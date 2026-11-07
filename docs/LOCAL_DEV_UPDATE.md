# Local dev synchronization, 7 November 2026

Merged origin/dev e86f0c5 into the local QA checkout at 5e0822e. This preserves the local test-bot history while adopting dev's login, case history/category/pagination/delete controls, bulk uploads, document-type saves, audit decoder and AI-schema corrections. No remote branch was pushed by this update.

Overlapping implementations were reconciled using dev's canonical provider schema module and frontend types/view. The local provider_schema import is now a compatibility alias. Local regression coverage and the server actor-ID provenance display were retained. The positive-case bot was updated to sign in through dev's local auth routes without placing credentials/cookies in reports.

Before the merge, the live SQLite database was backed up to an ignored timestamped .runtime/full-cycle-before-dev-*.db file. The updated server was restarted on the same local address and database only after checking that no analyses were in flight. Schema bootstrap remained version 2 and foreign-key validation passed.

Counts before and after restart were identical: 5 cases, 41 documents, 6 analysis jobs, 7 AI executions, 5 findings, 0 reviews and 65 audit events. Existing uploaded files and local configuration were preserved. No provider generation or fresh positive-case run was initiated during synchronization.

The app remains at http://127.0.0.1:8002. Local login is enabled; the operator username/password are configured in the ignored .env and are intentionally omitted from this report. Login returned 200, an unauthenticated business read correctly returned 401, authenticated case history returned all 5 cases, and the retained positive runner authenticated/read history successfully.

Validation passed: 316 backend tests, all 60 frontend Node tests, TypeScript checking and production Vite build. Full backend result is recorded in .tools/qa-results/dev-update-backend-final.log/XML. Earlier synchronization run: 315 passed; the final 316 includes the new runner-login regression. A dependency deprecation warning remains informational. Updated source and test results do not certify a new live provider E2E run.

An unrelated pre-existing local edit in backend/app/core/config.py remains uncommitted. The local .env credentials and runtime databases are excluded from Git. Any later authorized push must target fauzan, not dev.
