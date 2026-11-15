"use client";
import { useState } from "react";
import { api, money, RunOut } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

type Claim = { claim: string; label: string; evidence: { id: string; title: string; source?: string }[] };
export type ProposalPayload = {
  kind: "proposal";
  job: { job_id: string; title: string };
  draft: { cover_letter: string; screening_answers: string[]; revision: number };
  claims: Claim[];
  price_quote: { amount: number; basis: string; rationale: string[]; connects_cost: number; connects_usd: number };
  risk_report: { score: number; flags: string[]; explanation: string };
  critiques: { passed: boolean; issues: string[]; revision: number }[];
  compliance: { violations: string[]; allowed: boolean } | null;
  dry_run_preview: { cost_connects: number; connects_balance_after: number | null; would_send?: Record<string, unknown> };
};

/** Renders the letter with supported claims underlined; hover/focus shows the evidence behind each. */
function Annotated({ text, claims, evidence }: { text: string; claims: Claim[]; evidence: Record<string, { text: string; type: string }> }) {
  const parts: (string | Claim)[] = [text];
  for (const c of claims) {
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (typeof p !== "string") continue;
      const at = p.indexOf(c.claim);
      if (at === -1) continue;
      parts.splice(i, 1, p.slice(0, at), c, p.slice(at + c.claim.length));
      break;
    }
  }
  return (
    <p style={{ whiteSpace: "pre-wrap", margin: 0 }} data-testid="annotated-letter">
      {parts.map((p, i) => typeof p === "string" ? <span key={i}>{p}</span> : (
        <span key={i} className={`claim ${p.label}`} tabIndex={0} aria-label={`claim backed by ${p.evidence.map((e) => e.title).join(", ")}`}>
          {p.claim}
          <span className="tip" role="tooltip">
            <strong>{p.label.replace("_", " ")}</strong>
            {p.evidence.map((e) => (
              <span key={e.id} style={{ display: "block", marginTop: 6 }}>
                <strong>{e.title}</strong> <span className="muted">[{e.id}]</span><br />
                {(evidence[e.id]?.text ?? "").slice(0, 260)}
              </span>
            ))}
          </span>
        </span>
      ))}
    </p>
  );
}

export function ProposalStudio({ payload, evidence, onRun }: {
  payload: ProposalPayload; evidence: Record<string, { text: string; type: string }>; onRun: (r: RunOut) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(payload.draft.cover_letter);
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  async function decide(body: Record<string, unknown>) {
    setBusy(true); setErr(null);
    try { onRun(await api<RunOut>(`/approvals/jobs/${payload.job.job_id}`, { method: "POST", json: body })); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  }
  const last = payload.critiques[payload.critiques.length - 1];
  return (
    <section className="panel" aria-label="Proposal studio" data-testid="proposal-studio">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Proposal studio</h2>
        <span className="badge warn">waiting for your approval</span>
      </div>
      {payload.compliance?.violations?.length ? (
        <div className="banner warn small" style={{ marginTop: 10 }}>Compliance changed this text: {payload.compliance.violations.join("; ")}</div>
      ) : null}
      <div className="grid2" style={{ marginTop: 12 }}>
        <div>
          {editing ? (
            <>
              <textarea aria-label="Edit proposal" value={text} onChange={(e) => setText(e.target.value)} />
              <div className="small muted">{words} words · your edit is re-checked by Compliance and saved to style memory</div>
            </>
          ) : <Annotated text={payload.draft.cover_letter} claims={payload.claims} evidence={evidence} />}
          {payload.draft.screening_answers.length > 0 && (
            <>
              <h3 style={{ marginTop: 14 }}>Screening answers</h3>
              <ol className="small">{payload.draft.screening_answers.map((a, i) => <li key={i}>{a}</li>)}</ol>
            </>
          )}
        </div>
        <div className="small" style={{ display: "grid", gap: 10, alignContent: "start" }}>
          <div><h3>What will be sent</h3>
            Bid <strong>{money(payload.price_quote.amount)}{payload.price_quote.basis === "hourly" ? "/h" : ""}</strong> ·
            costs <strong>{payload.dry_run_preview.cost_connects} Connects</strong> (${payload.price_quote.connects_usd}) ·
            balance after {payload.dry_run_preview.connects_balance_after ?? "–"}</div>
          <div><h3>Price rationale</h3><ul>{payload.price_quote.rationale.map((r, i) => <li key={i}>{r}</li>)}</ul></div>
          <div><h3>Risk {Math.round(payload.risk_report.score * 100)}%</h3>{payload.risk_report.explanation}</div>
          <div><h3>Critic</h3>{payload.critiques.length} review(s); {last?.passed ? "passed" : `open issues: ${last?.issues.join("; ")}`}</div>
          <div><h3>Claims</h3>{payload.claims.filter((c) => c.label === "supported").length} supported,{" "}
            {payload.claims.filter((c) => c.label === "partly_supported").length} partly supported. Hover underlined text to see the evidence.</div>
        </div>
      </div>
      <ErrorBox error={err} />
      {rejecting ? (
        <div className="row" style={{ marginTop: 12 }}>
          <input aria-label="Reason for rejecting" placeholder="Why? (helps tune decisions)" value={reason} onChange={(e) => setReason(e.target.value)} style={{ flex: 1 }} />
          <button className="danger" disabled={busy} onClick={() => decide({ action: "reject", reason })}>Confirm reject</button>
          <button onClick={() => setRejecting(false)}>Cancel</button>
        </div>
      ) : (
        <div className="row" style={{ marginTop: 12 }}>
          {editing ? (
            <>
              <button className="primary" disabled={busy || words < 10} onClick={() => decide({ action: "edit", edited_text: text })}>Save edit and approve</button>
              <button onClick={() => { setEditing(false); setText(payload.draft.cover_letter); }}>Discard edit</button>
            </>
          ) : (
            <>
              <button className="primary" disabled={busy} onClick={() => decide({ action: "approve" })}>Approve and submit</button>
              <button onClick={() => setEditing(true)}>Edit</button>
            </>
          )}
          <button className="danger" onClick={() => setRejecting(true)}>Reject</button>
        </div>
      )}
    </section>
  );
}
