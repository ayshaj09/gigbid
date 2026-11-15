"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, JobRow, pct } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";

const COLS: [string, string[]][] = [
  ["Queued / running", ["queued", "running", "waiting_for_marketplace"]],
  ["Watching", ["watching"]],
  ["Needs your approval", ["awaiting_approval"]],
  ["Submitted", ["submitted"]],
  ["Closed", ["skipped", "rejected", "blocked", "needs_attention", "dead_letter"]],
];

export default function Pipeline() {
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { api<JobRow[]>("/jobs").then(setJobs).catch(setErr); }, []);
  if (!jobs) return <><ErrorBox error={err} /><Loading /></>;
  return (
    <>
      <h1>Pipeline</h1>
      <div className="kanban">
        {COLS.map(([title, statuses]) => {
          const items = jobs.filter((j) => statuses.includes(j.status ?? ""));
          return (
            <section className="col" key={title} aria-label={title}>
              <h3>{title} <span className="muted small">({items.length})</span></h3>
              {items.map((j) => (
                <div className="card" key={j.job_id}>
                  <Link href={`/jobs/${j.job_id}`}>{j.title}</Link>
                  <div className="small muted">fit {pct(j.fit)} · risk {pct(j.risk)}{j.is_scam ? " · scam" : ""}</div>
                </div>
              ))}
            </section>
          );
        })}
      </div>
    </>
  );
}
