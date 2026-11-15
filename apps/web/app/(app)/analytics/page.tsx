"use client";
import { useEffect, useState } from "react";
import { api, pct } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";

type A = { jobs_analysed: number; by_action: Record<string, number>; bids_submitted: number; connects_spent: number; replies: number;
  reply_rate: number | null; approvals: Record<string, number>; edit_rate: number | null; rejection_reasons: string[];
  usd_per_proposal: number | null; tokens_per_job: number; p50_latency_s: number | null; p95_latency_s: number | null };

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="panel"><div className="small muted">{label}</div><div className="stat">{value}</div></div>;
}

export default function Analytics() {
  const [a, setA] = useState<A | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { api<A>("/analytics").then(setA).catch(setErr); }, []);
  if (!a) return <><ErrorBox error={err} /><Loading /></>;
  const max = Math.max(1, ...Object.values(a.by_action));
  return (
    <>
      <h1>Analytics</h1>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
        <Stat label="Jobs analysed" value={a.jobs_analysed} />
        <Stat label="Bids submitted" value={a.bids_submitted} />
        <Stat label="Reply rate" value={pct(a.reply_rate)} />
        <Stat label="Connects spent" value={a.connects_spent} />
        <Stat label="Edit rate" value={pct(a.edit_rate)} />
        <Stat label="Cost / proposal" value={a.usd_per_proposal == null ? "–" : `$${a.usd_per_proposal.toFixed(4)}`} />
        <Stat label="p95 latency / job" value={a.p95_latency_s == null ? "–" : `${a.p95_latency_s}s`} />
        <Stat label="Tokens / job" value={a.tokens_per_job} />
      </div>
      <div className="grid2" style={{ marginTop: 16 }}>
        <section className="panel"><h2 style={{ marginTop: 0 }}>Decisions</h2>
          {Object.entries(a.by_action).map(([k, v]) => (
            <div key={k} className="small" style={{ margin: "6px 0" }}>{k} <span className="muted">({v})</span>
              <div className="bar" style={{ width: `${(v / max) * 100}%` }} role="img" aria-label={`${k}: ${v}`} /></div>
          ))}
        </section>
        <section className="panel"><h2 style={{ marginTop: 0 }}>Approvals</h2>
          <p className="small">approved {a.approvals.approve ?? 0} · edited {a.approvals.edit ?? 0} · rejected {a.approvals.reject ?? 0}</p>
          <h3>Recent rejection reasons</h3>
          {a.rejection_reasons.length ? <ul className="small">{a.rejection_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : <p className="small muted">None yet.</p>}
        </section>
      </div>
    </>
  );
}
