# ProcureMind V4.1 contract lock

Branch: main. Documentation verified against the supplied 39-page API Contract & Integration Specification v1.1. Section 2.3 controls. The project remains documentation-only after the requested cleanup; runtime implementation and foundation verification are pending.

## Files created

- [docs/CONTRACT_LOCK.md](docs/CONTRACT_LOCK.md): exact 36-endpoint inventory, success codes/scopes, all 12 Appendix A enums, canonical envelopes, headers, concurrency, provenance and integrity rules.
- [docs/contract_snapshot.json](docs/contract_snapshot.json): source hash and machine-readable endpoint, enum and Appendix B error inventory.
- [docs/CONTRACT_GAPS.md](docs/CONTRACT_GAPS.md): clean-case proposed addendum, supplier dataset separation and explicit source conflicts/unspecified decisions.
- [docs/OWNERSHIP.md](docs/OWNERSHIP.md): user-assigned boundaries and Teguh review requirement for shared models/schemas.
- [docs/VERIFICATION.md](docs/VERIFICATION.md): executed source checks and unexecuted foundation/runtime checks.
- README.md: navigation and installation status.

No backend, frontend or teammate-owned feature is implemented here. Corrections are PROPOSED; no enum or route was added to the contract.

## Installation and run commands

No install/run command can run against the current tree: backend/app/main.py, backend/pyproject.toml, frontend/package.json and tests have not been recreated. The following is a PROPOSED runbook for the future shared foundation, conditional on those manifests and scripts being supplied:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./backend[test]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

In another terminal from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
cd frontend
npm install
npm run typecheck
npm run dev
```

Prerequisites for that future scaffold: Python 3.11+ and Node/npm. These commands were not executed for this documentation-only version. Required verification URLs are /api/v1/health and /openapi.json; their contract exception is recorded in the gap register.

## Lock and integration boundaries

Source transcription is verified; open gaps are not approved changes, and runtime compliance is not established. Named ownership follows the user: Frontend Lead for frontend/src/**; Teguh for shared/core and business AI/document integration; Aris for simulation; Fazhima for assurance/review/audit QA. Shared models/schemas require Teguh review.

Clean cases must not gain fake repair proposals or APPROVE_CASE. Golden simulation uses contract prices 660M/690M/825M IDR; the separate 710M/835M/680M negative pack stays a different data version. No commit or push is performed by creating these documents.
