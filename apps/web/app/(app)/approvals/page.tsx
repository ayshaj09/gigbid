"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, money } from "@/lib/api";
import { Empty, ErrorBox, Loading } from "@/components/ui";

type Pending = { kind: "proposal" | "message"; target_id: string; payload: any };

export default function Approvals() {
  const [items, setItems] = useState<Pending[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { api<Pending[]>("/approvals").then(setItems).catch(setErr); }, []);
  return (
    <>
      <h1>Waiting for your approval</h1>
      <p className="muted small">These survive refreshes and restarts: each is a paused graph thread in the checkpointer.</p>
      <ErrorBox error={err} />
      {!items ? <Loading /> : items.length === 0 ? <Empty>Nothing waiting. New drafts appear here.</Empty> : (
        <div style={{ display: "grid", gap: 10 }}>
          {items.map((p) => (
            <div className="panel row" key={p.kind + p.target_id} style={{ justifyContent: "space-between" }}>
              <div>
                <span className="badge">{p.kind}</span>{" "}
                <strong>{p.kind === "proposal" ? p.payload.job.title : `Reply on ${p.target_id}`}</strong>
                <div className="small muted">
                  {p.kind === "proposal" ? `${money(p.payload.price_quote.amount)} · ${p.payload.dry_run_preview.cost_connects} Connects`
                    : `intent: ${p.payload.intent.intent}`}
                </div>
              </div>
              <Link className="btn" href={p.kind === "proposal" ? `/jobs/${p.target_id}` : `/messages?thread=${p.target_id}`}>Review</Link>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
