# Teguh branch foundation transfer

Source: main / origin/main commit 45b0c9ed00383f24a01ec3a2b07a038d34b89dff. Destination: teguh. Files were selectively copied; no main merge and no unrelated teammate source was introduced.

## Included

- Backend main, core configuration/database/security/bootstrap and response envelope.
- Shared schemas/enums and full shared model declarations needed for integration.
- Teguh router skeletons: cases, documents, analyses, jobs, findings, challenges, repairs.
- Backend dependency manifests/lock and foundation tests.
- Contract lock/snapshot, gap register, ownership, foundation OpenAPI and provenance-aware verification report.
- Environment example, ignore rules and AGENTS.md.

The route registry is adapted to import only Teguh routers. README.md and FOUNDATION_FILES.md describe this branch. Services/ai and services/documents are future Teguh work; main contains no such implementations to copy. Earlier pre-cleanup PDF helpers were not resurrected.

## Excluded

Frontend source; simulation router/services/fixtures/tests; review/audit routers; assurance services. Existing ignored local dependencies/cache directories may remain on disk from main, but are not copied into the branch or committed. Shared AI/simulation/review/audit table declarations remain present as shared contract infrastructure.

## Verification

Command: `.\.venv\Scripts\python.exe -m pytest backend/tests -q`.

Result: 14 passed, one existing Starlette/httpx deprecation warning. Backend imports/startup, health/OpenAPI, schemas, SQLite and immutable model guards pass. No business feature endpoints are implemented. No frontend check was run for this backend-only transfer. The full-foundation verification copied from main is marked as source-branch evidence.

## Remaining dependencies

Implement Teguh-owned P0 services and contract routes in this branch. Teammate routers join later in the integration branch. Honor recorded contract gaps and shared-schema review. This transfer makes no change to main or any other team branch.
