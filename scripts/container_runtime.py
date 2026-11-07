"""Dedicated local Docker demo: migrate versioned storage, then serve one worker."""
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import uvicorn


def prepare_identity(data: Path):
    data.mkdir(parents=True, exist_ok=True)
    identity = data / "demo-actor.json"
    if not identity.exists():
        with identity.open("x") as output:
            json.dump({"actor_id": str(uuid4())}, output)
        identity.chmod(0o600)
    actor = UUID(json.loads(identity.read_text())["actor_id"])
    if actor.version != 4:
        raise ValueError("Persisted demo actor must be UUID v4")
    os.environ["PROCUREMIND_DEMO_ACTOR_ID"] = str(actor)
    os.environ.setdefault("PROCUREMIND_DEMO_ROLE", "REVIEWER")
    os.environ.setdefault("PROCUREMIND_DEMO_DISPLAY_NAME", "Local Admin")
    contract = json.loads((Path(__file__).resolve().parents[1] / "docs/contract_snapshot.json").read_text())
    os.environ.setdefault("PROCUREMIND_DEMO_SCOPES", json.dumps(sorted({e["scope"] for e in contract["endpoints"]})))


def main():
    prepare_identity(Path("/data"))
    from app.core.config import get_settings
    from app.core.database import build_engine
    from app.core.demo_bootstrap import bootstrap
    from app.core.login import LoginSettings
    LoginSettings()  # Fail closed before provisioning if login is misconfigured.
    engine = build_engine(get_settings().database_url)
    try:
        bootstrap(engine)
    finally:
        engine.dispose()
    uvicorn.run("app.web:create_web_app", factory=True, host="0.0.0.0", port=8000, workers=1)


if __name__ == "__main__":
    main()
