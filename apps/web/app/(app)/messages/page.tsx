"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, RunOut } from "@/lib/api";
import { RunProgress } from "@/components/RunProgress";
import { Empty, ErrorBox, Loading, StatusBadge } from "@/components/ui";

type ThreadRow = { thread_id: string; job_id: string; status: string; intent: string; last_message: string };
type Thread = { thread_id: string; status: string; messages: { id: string; sender: string; text: string }[];
  intent: { intent: string; notes?: string } | null;
  pending_approval: { draft: { text: string; proposed_slots: string[] }; compliance: { violations: string[] } | null } | null };

function ThreadView({ id, onChange }: { id: string; onChange: () => void }) {
  const [t, setT] = useState<Thread | null>(null);
  const [run, setRun] = useState<RunOut | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => api<Thread>(`/threads/${id}`).then((x) => { setT(x); setText(x.pending_approval?.draft.text ?? ""); }).catch(setErr), [id]);
  useEffect(() => { load(); }, [load]);
  async function go(path: string, json?: unknown) {
    try { setRun(await api<RunOut>(path, { method: "POST", json })); } catch (e) { setErr(e); }
  }
  if (!t) return <><ErrorBox error={err} /><Loading /></>;
  const draft = t.pending_approval?.draft;
  return (
    <section className="panel" aria-label={`Thread ${id}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Thread {id}</h2>
        <div className="row"><StatusBadge s={t.status} />{t.intent && <span className={`badge ${t.intent.intent === "scam_signal" ? "bad" : ""}`}>{t.intent.intent.replaceAll("_", " ")}</span>}</div>
      </div>
      <div style={{ display: "grid", gap: 8, margin: "12px 0" }}>
        {t.messages.map((m) => (
          <div key={m.id} className="card" style={{ marginLeft: m.sender === "freelancer" ? 60 : 0, marginRight: m.sender === "client" ? 60 : 0 }}>
            <div className="small muted">{m.sender}</div>{m.text}
          </div>
        ))}
      </div>
      {run && <RunProgress run={run} onDone={() => { setRun(null); load(); onChange(); }} />}
      {draft ? (
        <>
          <h3>Suggested reply</h3>
          {t.pending_approval?.compliance?.violations?.length ? <p className="small banner warn">Compliance: {t.pending_approval.compliance.violations.join("; ")}</p> : null}
          <textarea aria-label="Reply text" style={{ minHeight: 120 }} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={() => go(`/approvals/threads/${id}`, text === draft.text ? { action: "approve" } : { action: "edit", edited_text: text })}>
              {text === draft.text ? "Approve and send" : "Send edited reply"}</button>
            <button className="danger" onClick={() => go(`/approvals/threads/${id}`, { action: "reject", reason: "declined in UI" })}>Don&apos;t send</button>
          </div>
        </>
      ) : (
        <button onClick={() => go(`/threads/${id}/process`)}>Check for new messages and draft a reply</button>
      )}
      <ErrorBox error={err} />
    </section>
  );
}

function Messages() {
  const params = useSearchParams();
  const router = useRouter();
  const sel = params.get("thread");
  const [rows, setRows] = useState<ThreadRow[] | null>(null);
  const [newId, setNewId] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => api<ThreadRow[]>("/threads").then(setRows).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  return (
    <>
      <h1>Messages</h1>
      <form className="row" style={{ marginBottom: 12 }} onSubmit={(e) => { e.preventDefault(); router.push(`/messages?thread=${encodeURIComponent(newId)}`); }}>
        <input aria-label="Thread id" placeholder="Thread id, e.g. T-1" value={newId} onChange={(e) => setNewId(e.target.value)} />
        <button type="submit" disabled={!newId}>Open thread</button>
      </form>
      <ErrorBox error={err} />
      <div className="grid2" style={{ gridTemplateColumns: "280px 1fr" }}>
        <div>{!rows ? <Loading /> : rows.length === 0 ? <Empty>No conversations processed yet.</Empty> : rows.map((r) => (
          <button key={r.thread_id} className="card" style={{ width: "100%", textAlign: "left", display: "block" }} onClick={() => router.push(`/messages?thread=${r.thread_id}`)}>
            <strong>{r.thread_id}</strong> <StatusBadge s={r.status} />
            <div className="small muted">{(r.last_message ?? "").slice(0, 80)}</div>
          </button>
        ))}</div>
        <div>{sel ? <ThreadView key={sel} id={sel} onChange={load} /> : <Empty>Pick a thread.</Empty>}</div>
      </div>
    </>
  );
}

export default function MessagesPage() {
  return <Suspense fallback={<Loading />}><Messages /></Suspense>;
}
