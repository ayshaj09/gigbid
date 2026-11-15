// Typed API client. Types come from the FastAPI OpenAPI schema: `npm run gen:api`.
import type { components } from "./api-types";

export type JobRow = components["schemas"]["JobRow"];
export type RunOut = components["schemas"]["RunOut"];
export type Me = components["schemas"]["Me"];
export type Decision = components["schemas"]["Decision"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const KEY = "gigbid.token";

export const token = {
  get: () => (typeof window === "undefined" ? null : window.localStorage.getItem(KEY)),
  set: (t: string) => window.localStorage.setItem(KEY, t),
  clear: () => window.localStorage.removeItem(KEY),
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, body });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth")) {
    token.clear();
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export type RunEvent = { node: string; status?: string | null; error?: string | null; ts: number; trace_id?: string };

/** Subscribe to a run's Server-Sent Events. Returns an unsubscribe function. */
export function streamRun(eventsUrl: string, onEvent: (e: RunEvent) => void, onDone?: (last: RunEvent) => void) {
  const es = new EventSource(`${API_URL}${eventsUrl}?token=${encodeURIComponent(token.get() ?? "")}`);
  es.addEventListener("node", (m) => {
    const ev = JSON.parse((m as MessageEvent).data) as RunEvent;
    onEvent(ev);
    if (ev.node === "__end__") {
      es.close();
      onDone?.(ev);
    }
  });
  es.onerror = () => es.close();
  return () => es.close();
}

export const pct = (x?: number | null) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const money = (x?: number | null) => (x == null ? "–" : `$${Math.round(x).toLocaleString()}`);
