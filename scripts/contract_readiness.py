"""Compare current/local or remote OpenAPI with all 36 locked business routes.

Exit 1 is a blocked integration gate; it is never converted into a passing E2E.
Usage: python scripts/contract_readiness.py [--base-url http://127.0.0.1:8000]
"""
import argparse
import json
from pathlib import Path

import httpx

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def readiness(openapi):
    contract = json.loads((ROOT / "docs/contract_snapshot.json").read_text())
    rows = []
    for endpoint in contract["endpoints"]:
        path = "/api/v1" + endpoint["path"]
        op = openapi.get("paths", {}).get(path, {}).get(endpoint["method"].lower())
        ok = op is not None and str(endpoint["success_code"]) in op.get("responses", {})
        rows.append({"method": endpoint["method"], "path": path,
                     "status": "REGISTERED" if ok else "BLOCKED", "expected_status": endpoint["success_code"]})
    return {"contract_version": "1.1", "registered": sum(r["status"] == "REGISTERED" for r in rows),
            "required": len(rows), "release_ready": all(r["status"] == "REGISTERED" for r in rows),
            "note": "Registration is a preflight, not evidence that workflows or providers pass.", "routes": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.base_url:
        response = httpx.get(args.base_url.rstrip("/") + "/openapi.json", timeout=15)
        response.raise_for_status()
        schema = response.json()
    else:
        schema = create_app().openapi()
    result = readiness(schema)
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if result["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
