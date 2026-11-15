"use client";
import { ReactNode } from "react";

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="muted" role="status">{what}…</p>;
}
export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="err" role="alert">{error instanceof Error ? error.message : String(error)}</p>;
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="panel muted" style={{ textAlign: "center", padding: 32 }}>{children}</div>;
}
const TONE: Record<string, string> = {
  submitted: "ok", sent: "ok", bid: "ok", awaiting_approval: "warn", watching: "warn", watch: "warn",
  waiting_for_marketplace: "bad", skipped: "", skip: "", rejected: "bad", blocked: "bad", needs_attention: "bad",
  dead_letter: "bad", queued: "", running: "warn",
};
export function StatusBadge({ s }: { s?: string | null }) {
  if (!s) return <span className="badge">–</span>;
  return <span className={`badge ${TONE[s] ?? ""}`}>{s.replaceAll("_", " ")}</span>;
}
