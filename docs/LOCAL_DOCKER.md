# Local Docker testing

The same-origin web application includes login, case history, multi-PDF uploads,
post-upload document typing, and removal of mistakenly uploaded documents.
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

1. Sign in, create a case, then open **Case history** to search/reopen it.
2. Select several PDFs and choose **Upload selected PDFs**. Each file uses its
   own existing upload endpoint and idempotency key. Partial failures are shown
   separately; retry skips successful files.
3. Select the correct type on each uploaded row and choose **Save document type**.
   Newly uploaded files start as Other. A TOR and technical specification are
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

- Backend pytest: 298 passed (dependency deprecation warnings only).
- Frontend Node tests: 43 passed; TypeScript and production build passed.
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
