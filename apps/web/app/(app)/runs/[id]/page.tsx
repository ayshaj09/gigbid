"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, RunEvent } from "@/lib/api";
import { ErrorBox, Loading, StatusBadge } from "@/components/ui";

type RunInfo = { run_id: string; kind: string; target_id: string; status: string; events: RunEvent[]; started: number;
  finished: number | null; tokens: number | null; usd: number | null; error: string | null };

/** Agent run viewer: every node the graph executed, with timing, trace id and outcome. */
export default function RunViewer() {
  const { id } = useParams<{ id: string }>();
  const [r, setR] = useState<RunInfo | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    let alive = true;
    const tick = () => api<RunInfo>(`/runs/${id}`).then((x) => { if (!alive) return; setR(x); if (x.status === "running") setTimeout(tick, 800); }).catch(setErr);
    tick();
    return () => { alive = false; };
  }, [id]);
  if (!r) return <><ErrorBox error={err} /><Loading /></>;
  const t0 = r.started;
  return (
    <>
      <h1>Run {r.run_id}</h1>
      <p className="small muted">{r.kind} {r.target_id} · <StatusBadge s={r.status} /> · trace {r.events.find((e) => e.trace_id)?.trace_id ?? "–"}
        {r.finished ? ` · ${(r.finished - r.started).toFixed(2)} s` : ""} · {r.tokens ?? 0} tokens · ${(r.usd ?? 0).toFixed(4)}</p>
      <div className="panel" style={{ padding: 0 }}>
        <table><thead><tr><th>#</th><th>Node</th><th>Status after</th><th>t+ (s)</th></tr></thead><tbody>
          {r.events.map((e, i) => (
            <tr key={i}><td>{i + 1}</td><td>{e.node}</td><td>{e.status ? <StatusBadge s={e.status} /> : ""}{e.error ? <span className="err small"> {e.error}</span> : null}</td>
              <td>{(e.ts - t0).toFixed(3)}</td></tr>
          ))}</tbody></table>
      </div>
      {r.error && <p className="err">{r.error}</p>}
    </>
  );
}
