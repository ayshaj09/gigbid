"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, JobRow, money, pct, RunOut } from "@/lib/api";
import { RunProgress } from "@/components/RunProgress";
import { Empty, ErrorBox, Loading, StatusBadge } from "@/components/ui";

export default function Inbox() {
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [status, setStatus] = useState("");
  const [minFit, setMinFit] = useState("");
  const [q, setQ] = useState("");
  const [runs, setRuns] = useState<RunOut[]>([]);
  const [jobId, setJobId] = useState("");
  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (status) p.set("status", status);
    if (minFit) p.set("min_fit", String(+minFit / 100));
    if (q) p.set("q", q);
    api<JobRow[]>(`/jobs?${p}`).then(setJobs).catch(setErr);
  }, [status, minFit, q]);
  useEffect(load, [load]);
  async function scout() {
    setErr(null);
    try { const r = await api<RunOut[]>("/jobs/scout", { method: "POST", json: {} }); setRuns(r); if (!r.length) load(); } catch (e) { setErr(e); }
  }
  async function analyse(e: React.FormEvent) {
    e.preventDefault();
    try { const r = await api<RunOut>(`/jobs/${encodeURIComponent(jobId)}/analyze`, { method: "POST" }); setRuns([r]); setJobId(""); } catch (e) { setErr(e); }
  }
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Job inbox</h1>
        <div className="row">
          <form onSubmit={analyse} className="row">
            <input aria-label="Job id" placeholder="Job id, e.g. J-100" value={jobId} onChange={(e) => setJobId(e.target.value)} />
            <button type="submit" disabled={!jobId}>Analyse job</button>
          </form>
          <button className="primary" onClick={scout}>Scout saved searches</button>
        </div>
      </div>
      {runs.length > 0 && (
        <div style={{ display: "grid", gap: 8, marginBottom: 16 }}>
          {runs.map((r) => <div key={r.run_id}><strong className="small">{r.target_id}</strong><RunProgress run={r} onDone={load} /></div>)}
        </div>
      )}
      <div className="row" style={{ marginBottom: 12 }}>
        <label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          {["awaiting_approval", "submitted", "watching", "skipped", "rejected", "blocked", "waiting_for_marketplace", "queued"].map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
        </select></label>
        <label>Min fit %<input type="number" min={0} max={100} value={minFit} onChange={(e) => setMinFit(e.target.value)} style={{ width: 90 }} /></label>
        <label>Search title<input value={q} onChange={(e) => setQ(e.target.value)} /></label>
      </div>
      <ErrorBox error={err} />
      {!jobs ? <Loading /> : jobs.length === 0 ? (
        <Empty>No jobs yet. Click <strong>Scout saved searches</strong> or analyse a job by id.</Empty>
      ) : (
        <div className="panel" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Job</th><th>Status</th><th>Fit</th><th>Risk</th><th>Price</th><th>Connects</th><th>Why</th></tr></thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id}>
                  <td><Link href={`/jobs/${j.job_id}`}>{j.title ?? j.job_id}</Link><div className="small muted">{j.job_id} · {j.category}</div></td>
                  <td><StatusBadge s={j.status} />{j.is_scam ? <> <span className="badge bad">scam</span></> : null}</td>
                  <td>{pct(j.fit)}</td><td>{pct(j.risk)}</td><td>{money(j.price)}</td><td>{j.connects ?? "–"}</td>
                  <td className="small muted" style={{ maxWidth: 320 }}>{j.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
