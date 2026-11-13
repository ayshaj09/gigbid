"""Pricing Strategist: bid from market statistics, the client's budget and spend, and the user's floor;
decide whether the Connects cost is worth it."""
from __future__ import annotations

from agent.handoffs import PriceQuote
from agent.nodes.common import ctx_of, node
from agent.policy import applies, rules


def price(spec: dict, fit: dict, risk: dict, persona: dict, stats: dict, balance: int | None, cfg: dict) -> PriceQuote:
    rationale = []
    hourly = spec.get("budget_type") == "hourly"
    lo, hi = spec.get("budget_min") or 0.0, spec.get("budget_max") or 0.0
    market = (stats or {}).get("hourly" if hourly else "fixed") or {}
    floor = persona.get("hourly_rate_usd", 0) if hourly else persona.get("floor_usd", 0)
    if hi:
        band = (lo, hi)
        rationale.append(f"client budget {lo:.0f}-{hi:.0f} {'USD/h' if hourly else 'USD'}")
    elif market:
        band = (market["p25"], market["p75"])
        rationale.append(f"no budget given; market p25-p75 for {spec.get('category')} is {band[0]:.0f}-{band[1]:.0f}")
    else:
        band = (floor, floor * 1.5)
        rationale.append("no budget or market data; anchored on your floor")
    # stronger fit and a stronger client justify the upper part of the band
    position = 0.35 + 0.4 * fit.get("score", 0) + 0.15 * risk.get("client_quality", 0.5)
    amount = band[0] + (band[1] - band[0]) * min(position, 0.95)
    if market.get("p50") and not hi:
        amount = (amount + market["p50"]) / 2
    if amount < floor:
        rationale.append(f"raised to your floor {floor:.0f} (above the client's range: expect pushback)")
        amount = floor
    amount = round(amount) if hourly else round(amount / 25) * 25
    rationale.append(f"positioned at {position:.0%} of the band from fit {fit.get('score', 0):.2f} "
                     f"and client quality {risk.get('client_quality', 0):.2f}")

    connects = spec.get("connects_cost", 0)
    for r in rules(cfg, "pricing"):
        if r["type"] == "connects_surcharge" and applies(r, spec.get("category")):
            connects += r["extra_connects"]
            rationale.append(f"policy {r.get('id', '')}: +{r['extra_connects']} connects")
        if r["type"] == "connects_multiplier" and applies(r, spec.get("category")):
            connects = int(round(connects * r["factor"]))
            rationale.append(f"policy {r.get('id', '')}: connects x{r['factor']}")
    usd_per = cfg["connects"]["usd_per_connect"]
    connects_usd = connects * usd_per
    expected_value = amount * (40 if hourly else 1) * (0.05 + 0.25 * fit.get("score", 0))  # crude win prob
    ratio = expected_value / connects_usd if connects_usd else float("inf")
    worth = ratio >= cfg["connects"]["min_value_ratio"]
    rationale.append(f"{connects} connects = ${connects_usd:.2f}; expected value ${expected_value:.0f} "
                     f"({ratio:.0f}x, need {cfg['connects']['min_value_ratio']:.0f}x)")
    if balance is not None and balance < connects:
        worth = False
        rationale.append(f"only {balance} connects left this week")
    return PriceQuote(amount=amount, basis="hourly" if hourly else "fixed", fair_band=band, connects_cost=connects,
                      connects_usd=round(connects_usd, 2), connects_worth_it=worth, rationale=rationale)


@node("pricing")
async def pricing(state, runtime):
    ctx = ctx_of(runtime)
    spec = state["job_spec"]
    mp = ctx.marketplace("pricing")
    stats = await mp.get_market_stats(spec.get("category") or "other")
    balance = (await mp.get_connects_balance()).get("balance")
    quote = price(spec, state["fit_report"], state["risk_report"], ctx.persona, stats, balance, ctx.cfg)
    out = {"price_quote": quote.model_dump()}
    if not quote.connects_worth_it:
        out.update(status="watching", status_reason="connects cost not justified: " + quote.rationale[-1],
                   decision={**state["decision"], "action": "watch",
                             "reasons": state["decision"]["reasons"] + ["connects not worth it"]})
    return out
