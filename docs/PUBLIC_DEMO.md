# Public dev demo via GitHub Codespaces

The same-origin entrypoint app.web:create_web_app serves the production React build and FastAPI on port 8000. It is a real backend, with no seeded findings, canned AI responses or replacement simulation calculations.

## Run locally

```powershell
.\.venv\Scripts\python.exe scripts/demo_runtime.py setup --skip-install
.\.venv\Scripts\python.exe scripts/demo_runtime.py start
```

Fresh environments can use `python scripts/demo_runtime.py setup` to create .venv, install backend/frontend dependencies and build. The script uses a dedicated ignored .runtime/demo.db and .runtime/pdfs, and a generated backend demo actor. It does not overwrite existing application databases or commit an API key. The demo operator role/scopes are explicitly configured server-side; public visitors share that visibly labeled demo context. Use synthetic/nonconfidential documents only. Live OpenAI features need an authorized backend key/model; no key is bundled into frontend assets or automatically transferred to GitHub.

## GitHub Codespaces

.devcontainer/devcontainer.json installs/builds on creation, then starts the app on resume. Codespaces uses the account's compute/storage quota. The minimum available machine has two cores. Port 8000 is forwarded; it must be changed to public through authenticated GitHub CLI or the Codespaces Ports UI. The resulting *.app.github.dev URL serves both UI and /api/v1; no CORS or localhost API URL is embedded into the production frontend. The URL works while the Codespace runs, not as permanent static GitHub Pages hosting.

## Owner composition and migration

Demo bootstrap runs checksum-verified Assurance migrations first, then core migration 0002, then reestablishes any missing original Assurance guards and installs Simulation's own immutable guards. The core legacy table rebuild now preserves attached owner triggers and uses/restores SQLite's legacy-alter setting during its transaction. No owner migration SQL or decision/calculation logic is changed.

The web composition delegates audit appends to Assurance's existing append primitive. Read-only adapters translate persisted CaseAccess membership into the owner services' case-grant/simulation-access ports. They never use browser identity headers, synthesize findings or change review semantics.

The wider Assurance test fixture migration mismatch recorded in DEV_MERGE_VERIFICATION.md remains a separate integration task; this dedicated demo bootstrap is independently tested. Browser visual QA and live OpenAI success are not claimed merely because the web server returns HTTP 200.
