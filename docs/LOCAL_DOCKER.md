# Local Docker testing

The same-origin web application includes login, case history, multi-PDF uploads,
post-upload document typing, case deletion, and removal of mistakenly uploaded documents.
This is a single-account demo deployment, not production OIDC or a multi-worker queue.

## Start

1. Install/start Docker Desktop.
2. Copy `.env.example` to `.env` if no local configuration exists; preserve an
   existing `.env`. Set `PROCUREMIND_LOGIN_USERNAME` and `PROCUREMIND_LOGIN_PASSWORD`
   in that ignored file. Never commit credentials. An OpenAI key/model can be
   supplied there for real AI calls; automated checks do not call a live provider.
3. From the repository root run:

   ```sh
   docker compose up -d --build
   docker compose ps
   ```

Open http://localhost:18000. The port is bound to loopback only. To choose a
port, set PROCUREMIND_HTTP_PORT before starting Compose. Login uses the local
credentials; the password is not built into the frontend or Docker image.

## Persistent storage

The named `procuremind_data` volume mounts `/data` and contains:

- `procuremind.db`: SQLite business records, audit and schema revisions.
- `pdfs/`: immutable uploaded PDF bytes.
- `demo-actor.json`: the stable backend actor UUID, so existing case memberships
  continue to work after container replacement.

The image runs as a non-root user and gives that user ownership of the new data
volume. Secrets, local databases, PDFs, node_modules and .env files are excluded
from the build context. Existing host preview databases are not imported or deleted;
Docker starts with its own volume. Do not mount an unversioned database into it.
The dedicated demo entrypoint explicitly applies the existing versioned migrations
before starting one Uvicorn worker. Unknown/unversioned schemas fail rather than
being overwritten. Back up the database and PDF files before future upgrades.

`docker compose restart` and `docker compose up -d --force-recreate` preserve the
volume. Session cookies are backed by process memory: sign in again after a restart.
The database, PDFs and actor identity remain. `docker compose down` stops/removes
containers while retaining data. `docker compose down -v` deletes the data volume;
do not use that option for a database you want to keep.

## Test the UI

1. Sign in, create a case, then open **Case history** to search/reopen it. Filter by Category and use Previous/Next to browse five newest-first cases per page. **Delete case** asks for confirmation and a reason; the existing server endpoint soft-deletes it with expected_version. Active analyses and reviewed cases remain protected; audit records and PDF bytes are retained.
2. Select several PDFs and choose **Upload selected PDFs**. Each file uses its
   own existing upload endpoint and idempotency key. Partial failures are shown
   separately; retry skips successful files.
3. Select the correct type on each uploaded row, then choose **Save document types**
   at the bottom beside **Continue to Assess**. One action saves each changed row
   through the existing versioned PATCH endpoint. On partial failure, successful
   rows stay saved; remaining selections stay available. A version conflict
   refreshes server metadata before another explicit save. Continue/analysis stay
   disabled while choices are unsaved. Newly uploaded files start as Other. A TOR and technical specification are
   required by the comparison UI before analysis.
4. To remove an incorrect file, select **Remove document**, confirm, and give a
   reason. The client sends reason and expected_version. The server soft-deletes
   the row; PDF bytes and history remain. Active-analysis or finalized-review
   restrictions are enforced by the server. No forced deletion or unlink occurs.
5. Recreate the container and sign in again. Reopen the case; document metadata,
   types, deletion state, and history should remain.

Useful commands:

```sh
docker compose logs --tail=100 app
docker compose restart app
docker compose up -d --force-recreate
```

The health check verifies HTTP liveness, not live AI/provider readiness. The clean-case
completion gap in v1.1 remains intentional; no APPROVE_CASE decision was added.

## Recorded local verification

- Backend pytest: 303 passed (dependency deprecation warnings only).
- Frontend Node tests: 51 passed; TypeScript and production build passed.
- Docker image built and container health check passed on local Docker Desktop.
- Authenticated HTTP smoke: create a clearly labelled synthetic case, upload two
  PDFs, change type, soft-delete one, verify case history/audit and logout.
- Container was force-recreated using the same volume; after a new login the
  case, document type, hash and deleted state remained correct.
- Both retained PDF byte hashes plus SQLite integrity/foreign-key checks passed
  after container recreation. Login sessions intentionally require re-login.

To repeat the synthetic persistence test from an installed backend/test environment:

```sh
python scripts/docker_smoke.py create
docker compose up -d --force-recreate
python scripts/docker_smoke.py verify
```

This creates a labelled synthetic case in the local volume. It neither runs AI
nor deletes other cases. Automated API/build tests were run; interactive visual
browser verification was not performed.

## Assess: provider failure versus frontend validation

An execution's `model` is null when no model response was received. The frontend
accepts that backend schema and shows the original job error; it does not replace
an absent runtime model with a requested model name. Missing/malformed fields
remain errors. A regression covers FAILED/AI_PROVIDER_ERROR with null model/usage.

If the container has no AI credentials, analysis correctly remains FAILED with
AI_PROVIDER_ERROR. Configure a valid, newly issued PROCUREMIND_OPENAI_API_KEY and
an available PROCUREMIND_OPENAI_MODEL in the ignored root .env. Do not paste keys
into chat or commit them. Recreate the container to load changed environment:

```sh
docker compose up -d --force-recreate
```

Sign in again and choose Run new analysis. Historical failed executions remain
immutable; a new request creates a new job rather than changing the old result.


## Provider schema compatibility

The provider adapters for analysis, challenge, and repair normalize Pydantic's
`format: uuid4` to the standard `format: uuid` with a UUID v4 pattern before sending
Structured Outputs schemas. OpenAI rejected the original schema with HTTP 400
invalid_json_schema, preventing any model response. The shared API models and
backend UUID4 validation remain unchanged. Regression tests cover all three
output schemas and rejection of non-v4 UUIDs.

Keep configuration in this order (values are placeholders):

```dotenv
PROCUREMIND_OPENAI_API_KEY=<secret API key>
PROCUREMIND_OPENAI_MODEL=gpt-6.1-sol
```

Never put the model name in the key variable or the key in the model variable.
The ignored local configuration was corrected and the model was verified through
a live synthetic provider request. No secrets are included in source or images.


The refreshed local Docker build also passed an authenticated live API smoke:
upload two synthetic PDFs as Other, save TOR/technical-specification types,
POST analysis (202), poll to COMPLETED with schema_valid=true and
evidence_validation_passed=true using gpt-6.1-sol, then soft-delete only the
synthetic test case and verify it no longer appears in case history. This was an
explicit live check, separate from the mocked automated test suite.


## Read the Assure summary

After analysis, open **Assure** to see the summary above the review controls.
Classify vendor proposals as **Supplier quotation** in Upload and save the types.
The table shows which proposals were inputs to the recorded analysis and links
any recorded findings to their evidence. A later upload requires a new analysis
before it appears as included. The selected correction's saved reviewer decision
and exact conclusion appear when a review exists. Reopen the case from history
or refresh resources to reload recorded results.

This summary uses the existing analysis/review; it makes no extra AI request.
The current analysis provides extracted requirements and integrity findings, not
a compliance verdict for every vendor requirement. A no-finding result therefore
remains distinct from vendor approval. Failed/incomplete processing, warnings,
and missing evidence stay visible. Existing clean-case completion restrictions
are preserved.


The summary update passed 63 frontend tests, TypeScript typecheck and production
build. The Docker image was rebuilt and became healthy. Authenticated HTTP checks
verified the new assets and case access, and the existing synthetic persistence
check verified retained document metadata/hash, deletion state, audit and logout.
Interactive visual browser verification was not performed.
