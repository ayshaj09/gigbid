"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";

type S = { effective: { thresholds: Record<string, number>; autonomy: { auto_skip_low_fit: boolean }; connects: { weekly_budget: number };
  model_profile: string; retrieval_variant: string; marketplace_mode: string;
  persona: { display_name: string; hourly_rate_usd: number; floor_usd: number; saved_searches: string[] } } };
type M = { style_rules: string[]; outcome_stats: Record<string, { n: number; reply_rate: number }>; edits_logged: number; promotion_rule: string };

export default function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [m, setM] = useState<M | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const load = () => {
    api<S>("/settings").then((x) => { setS(x); setForm({
      minimum_fit_score: x.effective.thresholds.minimum_fit_score, watch_fit_score: x.effective.thresholds.watch_fit_score,
      maximum_risk_score: x.effective.thresholds.maximum_risk_score, auto_skip_low_fit: x.effective.autonomy.auto_skip_low_fit,
      weekly_connects_budget: x.effective.connects.weekly_budget, hourly_rate_usd: x.effective.persona.hourly_rate_usd,
      floor_usd: x.effective.persona.floor_usd, saved_searches: x.effective.persona.saved_searches.join("\n") }); }).catch(setErr);
    api<M>("/memory").then(setM).catch(setErr);
  };
  useEffect(load, []);
  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg(""); setErr(null);
    try {
      await api("/settings", { method: "PUT", json: { ...form, saved_searches: String(form.saved_searches ?? "").split("\n").map((x) => x.trim()).filter(Boolean) } });
      setMsg("Saved. New runs use these settings."); load();
    } catch (e) { setErr(e); }
  }
  async function forget(rule: string) { await api(`/memory/style/${encodeURIComponent(rule)}`, { method: "DELETE" }); load(); }
  if (!s) return <><ErrorBox error={err} /><Loading /></>;
  const num = (k: string, step = 0.05, max?: number) => (
    <input type="number" step={step} min={0} max={max} value={String(form[k] ?? "")} onChange={(e) => setForm({ ...form, [k]: +e.target.value })} />
  );
  return (
    <>
      <h1>Settings</h1>
      <form className="panel" onSubmit={save} style={{ display: "grid", gap: 12 }}>
        <div className="row">
          <label>Bid if fit ≥{num("minimum_fit_score", 0.05, 1)}</label>
          <label>Watch if fit ≥{num("watch_fit_score", 0.05, 1)}</label>
          <label>Skip if risk &gt;{num("maximum_risk_score", 0.05, 1)}</label>
        </div>
        <div className="row">
          <label>Hourly rate (USD){num("hourly_rate_usd", 1)}</label>
          <label>Fixed-price floor (USD){num("floor_usd", 25)}</label>
          <label>Weekly Connects budget{num("weekly_connects_budget", 1)}</label>
        </div>
        <label className="row" style={{ display: "flex", color: "var(--ink)" }}>
          <input type="checkbox" checked={Boolean(form.auto_skip_low_fit)} onChange={(e) => setForm({ ...form, auto_skip_low_fit: e.target.checked })} />
          Let GigBid skip low-fit jobs on its own (it never sends anything on its own)
        </label>
        <label>Saved searches (one per line)<textarea style={{ minHeight: 80 }} value={String(form.saved_searches ?? "")} onChange={(e) => setForm({ ...form, saved_searches: e.target.value })} /></label>
        <p className="small muted" style={{ margin: 0 }}>Marketplace: {s.effective.marketplace_mode} · models: {s.effective.model_profile} · retrieval: {s.effective.retrieval_variant}</p>
        <ErrorBox error={err} />{msg && <p className="small" role="status">{msg}</p>}
        <div><button className="primary" type="submit">Save settings</button></div>
      </form>
      <section className="panel" style={{ marginTop: 16 }} aria-label="Memory viewer">
        <h2 style={{ marginTop: 0 }}>What GigBid has learned</h2>
        <p className="small muted">{m?.promotion_rule} · {m?.edits_logged ?? 0} edits logged</p>
        <h3>Style rules</h3>
        {m?.style_rules.length ? (
          <ul>{m.style_rules.map((r) => <li key={r} className="row">{r.replace("removed_phrase:", "never write: ").replace("cut_first_sentence", "drop the generic first sentence").replace("shortened", "write shorter")}
            <button className="danger" onClick={() => forget(r)} aria-label={`Forget ${r}`}>Forget</button></li>)}</ul>
        ) : <p className="small muted">None promoted yet.</p>}
        <h3>Outcome memory</h3>
        {m && Object.keys(m.outcome_stats).length ? (
          <ul className="small">{Object.entries(m.outcome_stats).map(([k, v]) => <li key={k}>{k}: {v.n} outcomes, reply rate {Math.round(v.reply_rate * 100)}%</li>)}</ul>
        ) : <p className="small muted">Needs 5 outcomes in a category first.</p>}
      </section>
    </>
  );
}
