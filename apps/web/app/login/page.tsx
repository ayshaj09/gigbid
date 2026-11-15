"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, token } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await api<{ token: string; onboarded: boolean }>(`/auth/${mode}`, { method: "POST", json: { email, password } });
      token.set(r.token);
      router.replace(r.onboarded ? "/" : "/onboarding");
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <div className="center">
      <form className="panel" style={{ width: 360, display: "grid", gap: 12 }} onSubmit={submit}>
        <h1>GigBid</h1>
        <p className="muted small" style={{ margin: 0 }}>Finds jobs, drafts grounded proposals. Nothing is sent without your approval.</p>
        <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
        <label>Password<input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        <ErrorBox error={err} />
        <button className="primary" disabled={busy} type="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
