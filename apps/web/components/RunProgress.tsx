"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { RunEvent, RunOut, streamRun } from "@/lib/api";

/** Live node-by-node progress of one graph run (SSE). */
export function RunProgress({ run, onDone }: { run: RunOut; onDone?: (status: string) => void }) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  useEffect(() => {
    setEvents([]);
    return streamRun(run.events_url, (e) => setEvents((xs) => [...xs, e]), (last) => onDone?.(last.status ?? ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.run_id]);
  const last = events[events.length - 1];
  return (
    <div className="panel" aria-live="polite" data-testid="run-progress">
      <div className="row small muted" style={{ justifyContent: "space-between" }}>
        <span>{last?.node === "__end__" ? `Finished: ${last.status}` : "Running…"}</span>
        <Link href={`/runs/${run.run_id}`}>Run viewer</Link>
      </div>
      <div className="progress" style={{ marginTop: 6 }}>
        {events.filter((e) => e.node !== "__interrupt__").map((e, i, arr) => (
          <span key={i} className={i === arr.length - 1 ? "cur" : ""}>{e.node === "__end__" ? "done" : e.node}</span>
        ))}
      </div>
      {last?.error ? <p className="err small">{last.error}</p> : null}
    </div>
  );
}
