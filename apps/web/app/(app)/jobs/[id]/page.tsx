"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, money, pct, RunOut } from "@/lib/api";
import { ProposalPayload, ProposalStudio } from "@/components/ProposalStudio";
import { RunProgress } from "@/components/RunProgress";
import { ErrorBox, Loading, StatusBadge } from "@/components/ui";

type Detail = {
  status: string; status_reason: string | null; pending_approval: ProposalPayload | null;
  job: { job_id: string; title: string; description: string; budget?: { min: number; max: number; type: string }; connects_cost: number; screening_questions: string[] };
  job_spec: { category: string; requirements: { id: string; text: string; must_have: boolean }[]; hidden_needs: string[]; timeline_days: number | null } | null;
  fit_report: { score: number; reasons: string[]; missing_skills: string[]; matrix: { requirement_id: string; requirement: string; evidence_ids: string[]; strength: string }[] } | null;
  risk_report: { score: number; flags: string[]; explanation: string; is_scam: boolean } | null;
  decision: { action: string; reasons: string[]; auto: boolean } | null;
  price_quote: { amount: number; basis: string; rationale: string[] } | null;
  proposal_draft: { cover_letter: string } | null;
  verification: { unsupported_before: number; removed: string[] } | null;
  submission: { proposal_id: string } | null;
  evidence: { evidence_id: string; title: string; type: string; text: string; source: string }[] | null;
  trace: { node: string; latency_s?: number }[];
};

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [run, setRun] = useState<RunOut | null>(null);
  const load = useCallback(() => {
    api<Detail>(`/jobs/${id}`).then((x) => { setD(x); setErr(null); }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) setD(null); setErr(e);
    });
  }, [id]);
  useEffect(load, [load]);
  async function analyse() { try { setRun(await api<RunOut>(`/jobs/${id}/analyze`, { method: "POST" })); } catch (e) { setErr(e); } }
  const evidence = Object.fromEntries((d?.evidence ?? []).map((e) => [e.evidence_id, e]));
  if (!d && !err) return <Loading />;
  return (
    <>
      <p className="small"><Link href="/">← Inbox</Link></p>
      {run && <div style={{ marginBottom: 12 }}><RunProgress run={run} onDone={() => { setRun(null); load(); }} /></div>}
      {!d ? (
        <div className="panel"><p>This job hasn&apos;t been analysed yet.</p><ErrorBox error={err instanceof ApiError && err.status === 404 ? null : err} />
          <button className="primary" onClick={analyse}>Analyse {id}</button></div>
      ) : (
        <>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h1 style={{ margin: 0 }}>{d.job.title}</h1>
            <div className="row"><StatusBadge s={d.status} /><button onClick={analyse} disabled={d.status === "awaiting_approval"}>Re-analyse</button></div>
          </div>
          <p className="muted small">{d.job.job_id} · {d.job_spec?.category} · budget {d.job.budget ? `${money(d.job.budget.min)}–${money(d.job.budget.max)} ${d.job.budget.type}` : "–"} · {d.job.connects_cost} Connects</p>
          {d.status_reason && <p className="small"><strong>Decision:</strong> {d.decision?.action}{d.decision?.auto ? " (automatic)" : ""} — {d.status_reason}</p>}
          {d.submission && <div className="banner warn" style={{ background: "var(--ok-bg)", color: "var(--ok)" }}>Submitted as {d.submission.proposal_id}.</div>}
          {d.pending_approval && !run && (
            // keyed by the draft text: a re-approval after Compliance changed an edit starts fresh
            <ProposalStudio key={d.pending_approval.draft.cover_letter} payload={d.pending_approval} evidence={evidence} onRun={setRun} />
          )}
          <div className="grid2" style={{ marginTop: 16 }}>
            <section className="panel"><h2 style={{ marginTop: 0 }}>Job post</h2>
              <p className="small" style={{ whiteSpace: "pre-wrap" }}>{d.job.description}</p>
              {d.job_spec?.hidden_needs?.length ? <p className="small"><strong>Hidden needs:</strong> {d.job_spec.hidden_needs.join(", ")}</p> : null}
            </section>
            <section className="panel"><h2 style={{ marginTop: 0 }}>Risk {pct(d.risk_report?.score)}</h2>
              <div className="row">{d.risk_report?.flags.map((f) => <span key={f} className="badge bad">{f.replaceAll("_", " ")}</span>)}</div>
              <p className="small">{d.risk_report?.explanation}</p>
              {d.price_quote && <><h3>Price {money(d.price_quote.amount)}{d.price_quote.basis === "hourly" ? "/h" : ""}</h3>
                <ul className="small">{d.price_quote.rationale.map((r, i) => <li key={i}>{r}</li>)}</ul></>}
            </section>
          </div>
          {d.fit_report && (
            <section className="panel" style={{ marginTop: 16 }}>
              <h2 style={{ marginTop: 0 }}>Fit {pct(d.fit_report.score)}: requirement → evidence</h2>
              <table><thead><tr><th>Requirement</th><th>Strength</th><th>Evidence</th></tr></thead><tbody>
                {d.fit_report.matrix.map((m) => (
                  <tr key={m.requirement_id}><td className="small">{m.requirement}</td>
                    <td><span className={`badge ${m.strength === "strong" ? "ok" : m.strength === "partial" ? "warn" : "bad"}`}>{m.strength}</span></td>
                    <td className="small">{m.evidence_ids.length ? m.evidence_ids.map((e) => <span key={e} title={evidence[e]?.text} style={{ display: "block" }}>{evidence[e]?.title ?? e}</span>) : <span className="muted">no evidence: not claimed</span>}</td></tr>
                ))}</tbody></table>
              <p className="small muted">{d.fit_report.reasons.join(" · ")}</p>
            </section>
          )}
          {d.verification && d.verification.unsupported_before > 0 && (
            <section className="panel small" style={{ marginTop: 16 }}><h3>Removed by claim verification</h3>
              <ul>{d.verification.removed.map((r, i) => <li key={i}>{r}</li>)}</ul></section>
          )}
        </>
      )}
    </>
  );
}
