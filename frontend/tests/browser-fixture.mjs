// Local UI verification only. No AI/backend integration is claimed by this server.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { fixtureBackend } from "./fixtures.mjs";
const backend = fixtureBackend();
const dist = path.resolve(fileURLToPath(new URL("../dist/", import.meta.url)));
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://127.0.0.1:18742");
    if (url.pathname === "/__test/state") { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify({ ...backend.state, idempotency: undefined })); return; }
    if (url.pathname === "/__test/mode" && req.method === "POST") { let body = ""; for await (const chunk of req) body += chunk; Object.assign(backend.state, JSON.parse(body)); res.end("ok"); return; }
    if (url.pathname.startsWith("/api/v1/") || url.pathname.startsWith("/auth/")) {
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      const bytes = Buffer.concat(chunks); const type = req.headers["content-type"] ?? "";
      const body = type.startsWith("multipart/") ? await new Response(bytes, { headers: { "Content-Type": type } }).formData() : bytes.length ? bytes.toString() : undefined;
      const result = await backend.fetcher(url.href, { method: req.method, headers: req.headers, body });
      res.writeHead(result.status, Object.fromEntries(result.headers)); res.end(await result.text()); return;
    }
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html";
    const file = path.resolve(dist, relative);
    if (!file.startsWith(dist + path.sep) && file !== path.join(dist, "index.html")) { res.writeHead(403); res.end(); return; }
    let content = await readFile(file); const ext = path.extname(file);
    if (ext === ".html") content = Buffer.from(content.toString().replace("<body>", '<body><div style="padding:10px;background:#fff2c9;color:#604400;font:12px Arial;text-align:center">SYNTHETIC FRONTEND TEST FIXTURE — no live AI or integrated backend</div>'));
    res.setHeader("Content-Type", ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css" })[ext] ?? "application/octet-stream"); res.end(content);
  } catch (error) { res.writeHead(500); res.end(String(error)); }
});
server.listen(18742, "127.0.0.1", () => process.stdout.write("TEST ONLY: http://127.0.0.1:18742\n"));
