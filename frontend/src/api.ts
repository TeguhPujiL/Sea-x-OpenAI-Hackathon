import { decodeEnvelope, ShapeError, object, type Decoder, type ApiErrorBody, type ApiMeta } from "./contracts";

export class RequestError extends Error {
  constructor(public status: number, public body: ApiErrorBody, public requestId?: string, public retryAfter?: string | null) { super(body.message); this.name = "RequestError"; }
}
export class TransportError extends Error {
  constructor() { super("The response could not be received. The server outcome may be unknown. Retry the same request, or refresh before starting a new operation."); this.name = "TransportError"; }
}
export interface ClientConfig { baseUrl: string; development: boolean }
export function readConfig(env: { VITE_API_BASE_URL?: string; DEV?: boolean }): ClientConfig {
  // Development fallback only. Production must explicitly supply VITE_API_BASE_URL.
  const value = env.VITE_API_BASE_URL?.trim() || (env.DEV ? "/api/v1" : "");
  if (!value) throw new Error("VITE_API_BASE_URL is required for production builds. Set it to your deployed /api/v1 endpoint.");
  const url = value.replace(/\/+$/, "");
  if (!/^\/(?!\/)[^?#]*$/.test(url) && !/^https?:\/\/[^\s?#]+$/.test(url)) throw new Error("VITE_API_BASE_URL must be a same-origin path or an HTTP(S) URL without query parameters.");
  if (/^https?:/.test(url) && (new URL(url).username || new URL(url).password)) throw new Error("Do not put credentials in VITE_API_BASE_URL.");
  return { baseUrl: url, development: !!env.DEV };
}
export function normalize(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(normalize).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${normalize((value as Record<string, unknown>)[key])}`).join(",")}}`;
  const result = JSON.stringify(value); if (result === undefined) throw new ShapeError("Undefined request values are not allowed."); return result;
}
export function requiresIdempotency(method: string, path: string): boolean {
  return method === "POST" && (/^\/cases$/.test(path) || /^\/cases\/[^/]+\/(documents|analyses|simulations|reviews)$/.test(path) || /^\/findings\/[^/]+\/repair-proposals$/.test(path));
}
export interface PreparedRequest<T> { method: string; path: string; idempotencyKey?: string; send(signal?: AbortSignal): Promise<T> }
type Fetch = typeof fetch;
export function createClient(config: ClientConfig, fetcher: Fetch = fetch, newId = () => crypto.randomUUID()) {
  let lastMeta: ApiMeta | null = null;
  function prepare<T>(method: string, path: string, decoder: Decoder<T>, options: { body?: unknown; status?: number; multipart?: FormData } = {}): PreparedRequest<T> {
    if (!path.startsWith("/") || path.startsWith("//")) throw new ShapeError("Invalid resource path.");
    const headers: Record<string, string> = { Accept: "application/json" };
    const key = requiresIdempotency(method, path) || method === "POST" && /^\/experimental\/cases\/[^/]+\/procurement-conclusions$/.test(path) ? newId() : undefined;
    if (key) headers["Idempotency-Key"] = key;
    let body: BodyInit | undefined;
    if (options.multipart) {
      // Capture immutable Blob/File references and string metadata once for transport retry.
      const entries = [...options.multipart.entries()]; const snapshot = new FormData();
      for (const [name, value] of entries) snapshot.append(name, value);
      body = snapshot; // Browser supplies the multipart boundary.
    } else if (options.body !== undefined) { body = normalize(options.body); headers["Content-Type"] = "application/json"; }
    let completed = false;
    let inFlight = false;
    let transportRetryAllowed = true;
    return { method, path, idempotencyKey: key, async send(signal) {
      if (completed || inFlight || !transportRetryAllowed) throw new Error("Create a new request for a new operation. Only an unresolved transport failure can reuse this request.");
      inFlight = true;
      try {
        let response: Response;
        try { response = await fetcher(`${config.baseUrl}${path}`, { method, headers: { ...headers }, body, signal, credentials: "same-origin" }); }
        catch (error) { if (signal?.aborted) throw error; throw new TransportError(); }
        // A received HTTP response completes this attempt: HTTP retries must use a new request.
        transportRetryAllowed = false;
        let raw: unknown;
        try { raw = await response.json(); }
        catch (error) {
          if (signal?.aborted) throw error;
          if (error instanceof TypeError) { transportRetryAllowed = true; throw new TransportError(); }
          throw new ShapeError(`HTTP ${response.status} returned non-JSON content. Verify the API URL and proxy configuration.`);
        }
        const envelope = decodeEnvelope(raw, config.development ? decoder : (value => { object(value); return decoder(value); }));
        lastMeta = envelope.meta;
        if (!envelope.success && response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("procuremind:session-expired"));
        if (!envelope.success) throw new RequestError(response.status, envelope.error, envelope.meta.request_id, response.headers.get("Retry-After"));
        if (response.status !== (options.status ?? 200)) throw new ShapeError(`Expected HTTP ${options.status ?? 200}, received ${response.status}.`);
        if (!response.ok) throw new ShapeError(`HTTP ${response.status} cannot carry a success envelope.`);
        completed = true; return envelope.data;
      } finally { inFlight = false; }
    } };
  }
  return { prepare, get: <T>(path: string, decoder: Decoder<T>, signal?: AbortSignal) => prepare("GET", path, decoder).send(signal), get lastMeta() { return lastMeta; } };
}
export type ApiClient = ReturnType<typeof createClient>;
