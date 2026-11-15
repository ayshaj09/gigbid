"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api, token } from "@/lib/api";

const NAV = [
  ["/", "Inbox"], ["/pipeline", "Pipeline"], ["/approvals", "Approvals"], ["/messages", "Messages"],
  ["/analytics", "Analytics"], ["/settings", "Settings"],
] as const;

type Status = { marketplace_ok: boolean; detail: string; queued_while_down: number; down_for_s: number };

export function StatusBanner() {
  const [st, setSt] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    const tick = () => api<Status>("/status").then((s) => alive && setSt(s)).catch(() => {});
    tick();
    const id = setInterval(tick, 15000);
    return () => { alive = false; clearInterval(id); };
  }, [n]);
  if (!st || st.marketplace_ok) {
    return st && st.queued_while_down ? (
      <div className="banner warn" role="status">{st.queued_while_down} job(s) were queued during an outage and will resume automatically.</div>
    ) : null;
  }
  return (
    <div className="banner bad" role="alert" data-testid="degraded-banner">
      <strong>Marketplace unavailable.</strong> New work is queued, nothing is lost; it resumes when the marketplace is back.
      {st.queued_while_down ? ` ${st.queued_while_down} job(s) waiting.` : ""}{" "}
      <button disabled={busy} onClick={async () => { setBusy(true); await api("/status/retry", { method: "POST" }).catch(() => {}); setBusy(false); setN(n + 1); }}>
        Retry now
      </button>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!token.get()) { router.replace("/login"); return; }
    api<{ onboarded: boolean }>("/auth/me")
      .then((me) => { if (!me.onboarded && path !== "/onboarding") router.replace("/onboarding"); else setReady(true); })
      .catch(() => router.replace("/login"));
  }, [path, router]);
  if (!ready) return <div className="center muted">Loading…</div>;
  if (path === "/onboarding") return <main style={{ margin: "0 auto" }}>{children}</main>;
  return (
    <div className="shell">
      <nav className="side" aria-label="Main">
        <div className="brand">GigBid</div>
        {NAV.map(([href, label]) => (
          <Link key={href} href={href} aria-current={path === href ? "page" : undefined}>{label}</Link>
        ))}
        <button style={{ marginTop: 24 }} onClick={() => { token.clear(); router.replace("/login"); }}>Sign out</button>
      </nav>
      <main><StatusBanner />{children}</main>
    </div>
  );
}
