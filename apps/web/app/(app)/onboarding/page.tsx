"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, API_URL, token } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";

type Persona = { persona_id: string; display_name: string; headline: string; skills: string[]; hourly_rate_usd: number; floor_usd: number; saved_searches: string[] };

export default function Onboarding() {
  const router = useRouter();
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [pid, setPid] = useState("");
  const [rate, setRate] = useState(40);
  const [floor, setFloor] = useState(300);
  const [budget, setBudget] = useState(80);
  const [searches, setSearches] = useState("");
  const [mode, setMode] = useState<"gigsim" | "upwork_live">("gigsim");
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { api<Persona[]>("/personas").then((p) => { setPersonas(p); if (p[0]) pick(p[0]); }).catch(setErr); }, []);
  function pick(p: Persona) {
    setPid(p.persona_id); setRate(p.hourly_rate_usd ?? 40); setFloor(p.floor_usd ?? 300); setSearches((p.saved_searches ?? []).join("\n"));
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null);
    try {
      if (file) {
        const fd = new FormData(); fd.append("file", file);
        const r = await fetch(`${API_URL}/portfolio/upload`, { method: "POST", body: fd, headers: { Authorization: `Bearer ${token.get()}` } });
        if (!r.ok) throw new Error((await r.json()).detail ?? "upload failed");
      }
      await api("/onboarding", { method: "POST", json: { persona_id: pid, hourly_rate_usd: rate, floor_usd: floor, weekly_connects_budget: budget,
        saved_searches: searches.split("\n").map((s) => s.trim()).filter(Boolean), marketplace_mode: mode } });
      router.replace("/");
    } catch (e) { setErr(e); }
  }
  if (!personas) return <Loading what="Loading personas" />;
  return (
    <form onSubmit={submit} style={{ maxWidth: 720, display: "grid", gap: 16 }}>
      <h1>Set up GigBid</h1>
      <fieldset className="panel"><legend>1. Your portfolio</legend>
        {personas.map((p) => (
          <label key={p.persona_id} className="row" style={{ color: "var(--ink)", display: "flex" }}>
            <input type="radio" name="persona" checked={pid === p.persona_id} onChange={() => pick(p)} />
            <span><strong>{p.display_name}</strong> <span className="muted small">{p.headline}</span></span>
          </label>
        ))}
        <label style={{ marginTop: 10 }}>Or add your own case study, CV or README (md, pdf, json, code)
          <input type="file" accept=".md,.txt,.pdf,.json,.py,.ts,.sql" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
      </fieldset>
      <fieldset className="panel row"><legend>2. Rates and budget</legend>
        <label>Hourly rate (USD)<input type="number" min={1} value={rate} onChange={(e) => setRate(+e.target.value)} /></label>
        <label>Fixed-price floor (USD)<input type="number" min={0} value={floor} onChange={(e) => setFloor(+e.target.value)} /></label>
        <label>Weekly Connects budget<input type="number" min={0} value={budget} onChange={(e) => setBudget(+e.target.value)} /></label>
      </fieldset>
      <fieldset className="panel"><legend>3. Saved searches (one per line)</legend>
        <textarea style={{ minHeight: 90 }} value={searches} onChange={(e) => setSearches(e.target.value)} aria-label="Saved searches" />
      </fieldset>
      <fieldset className="panel"><legend>4. Marketplace</legend>
        <label className="row" style={{ display: "flex", color: "var(--ink)" }}><input type="radio" checked={mode === "gigsim"} onChange={() => setMode("gigsim")} /> GigSim (course simulator)</label>
        <label className="row" style={{ display: "flex", color: "var(--ink)" }}><input type="radio" checked={mode === "upwork_live"} onChange={() => setMode("upwork_live")} /> Live Upwork via official MCP (drafts only; you confirm on Upwork)</label>
      </fieldset>
      <ErrorBox error={err} />
      <button className="primary" type="submit" disabled={!pid}>Finish setup</button>
    </form>
  );
}
