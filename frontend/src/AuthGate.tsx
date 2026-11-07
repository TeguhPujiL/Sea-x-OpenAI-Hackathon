import React, { useEffect, useState } from "react";
import App from "./App";
import { RequestError, type ClientConfig } from "./api";
import { decodeEnvelope, object } from "./contracts";
export interface LoginSession { authenticated: boolean; username: string | null; login_enabled: boolean }
function decodeSession(value: unknown): LoginSession {
  const v = object(value);
  if (typeof v.authenticated !== "boolean" || typeof v.login_enabled !== "boolean" || !(v.username === null || typeof v.username === "string")) throw new Error("Invalid sign-in response");
  return v as unknown as LoginSession;
}
export async function authRequest(config: ClientConfig, operation: "session" | "login" | "logout", body?: { username: string; password: string }, signal?: AbortSignal): Promise<LoginSession> {
  const base = /^https?:\/\//.test(config.baseUrl) ? new URL("/auth/", config.baseUrl).href : "/auth/";
  const response = await fetch(base + operation, { method: operation === "session" ? "GET" : "POST", credentials: "include", cache: "no-store", signal,
    headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
  let raw: unknown;
  try { raw = await response.json(); } catch { throw new Error("Sign-in service is unavailable. Start the combined web backend and try again."); }
  const envelope = decodeEnvelope(raw, decodeSession);
  if (!envelope.success) throw new RequestError(response.status, envelope.error, envelope.meta.request_id, response.headers.get("Retry-After"));
  if (!response.ok) throw new Error("Sign-in service returned an unexpected response");
  return envelope.data;
}
export function LoginForm({ busy, error, onLogin }: { busy: boolean; error: string | null; onLogin: (username: string, password: string) => Promise<void> }) {
  return <main className="login-page"><section className="panel login-card"><p className="eyebrow">PROCUREMIND V4.1</p><h1>Sign in to your workspace</h1><p>Open case history, manage evidence, and continue procurement reviews.</p>
    {error && <p className="notice error-notice" role="alert">{error}</p>}
    <form onSubmit={async e => { e.preventDefault(); const form = e.currentTarget; const data = new FormData(form); await onLogin(String(data.get("username") ?? ""), String(data.get("password") ?? "")); const password = form.elements.namedItem("password") as HTMLInputElement | null; if (password) password.value = ""; }}>
      <label className="field"><span>Username</span><input name="username" autoComplete="username" required maxLength={80} defaultValue="admin" disabled={busy} /></label>
      <label className="field"><span>Password</span><input name="password" type="password" autoComplete="current-password" required maxLength={256} disabled={busy} /></label>
      <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form><p className="muted">Access is verified by the server. Your password is never stored in browser storage.</p></section></main>;
}
export default function AuthGate({ config }: { config: ClientConfig }) {
  const [session, setSession] = useState<LoginSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    void authRequest(config, "session", undefined, controller.signal).then(setSession).catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Could not check sign-in"); });
    const expired = () => { setSession({ authenticated: false, username: null, login_enabled: true }); setError("Your session expired. Sign in to continue."); };
    window.addEventListener("procuremind:session-expired", expired);
    return () => { controller.abort(); window.removeEventListener("procuremind:session-expired", expired); };
  }, [config, attempt]);
  if (!session) return <main className="login-page"><section className="panel login-card"><h1>ProcureMind</h1>{error ? <><p role="alert">{error}</p><button className="secondary" onClick={() => setAttempt(n => n + 1)}>Retry connection</button></> : <p role="status">Checking sign-in…</p>}</section></main>;
  if (!session.authenticated) return <LoginForm busy={busy} error={error} onLogin={async (username, password) => {
    if (busy) return; setBusy(true); setError(null);
    try { setSession(await authRequest(config, "login", { username, password })); }
    catch (err) { setError(err instanceof Error ? err.message : "Sign-in failed"); }
    finally { setBusy(false); }
  }} />;
  return <App config={config} userName={session.login_enabled ? session.username ?? undefined : undefined} onLogout={session.login_enabled ? async () => { setSession(await authRequest(config, "logout")); } : undefined} />;
}
