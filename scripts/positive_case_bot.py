"""Run the real clean-positive PDF workflow against a local ProcureMind server.

No mocked AI, synthetic findings, fake repairs, or automatic generation retries.
Exit 0: passed; 1: failed; 2: clean assertions passed, final completion blocked by G01.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
TYPES = {"01": "TOR", "02": "TECHNICAL_SPECIFICATION", "03": "OWNER_COST_ESTIMATE",
         "04": "TECHNICAL_JUSTIFICATION", "05": "SUPPLIER_QUOTATION", "06": "WARRANTY_EVIDENCE",
         "07": "EVALUATION_REPORT", "09": "CONTRACT"}


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def inventory(dataset: Path):
    root = dataset.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Dataset must be a directory")
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for path in files:
        path.resolve().relative_to(root)  # Reject references outside the authorized folder.
    manifests = [p for p in files if p.name == "manifest_pdf.txt"]
    if len(manifests) != 1:
        raise ValueError("Exactly one manifest_pdf.txt control file is required")
    listed = [line.strip() for line in manifests[0].read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    pdfs = [p for p in files if p.suffix.lower() == ".pdf"]
    if len(listed) != len(set(listed)) or set(listed) != {p.relative_to(root).as_posix() for p in pdfs}:
        raise ValueError("PDF inventory differs from manifest_pdf.txt")
    if len(files) != len(pdfs) + 1:
        raise ValueError("Unexpected non-PDF file: only manifest_pdf.txt is a control file")
    result = []
    for path in pdfs:
        raw = path.read_bytes()
        if not raw.startswith(b"%PDF-"):
            raise ValueError(f"Invalid PDF signature: {path.name}")
        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            if doc.is_encrypted or not any(page.get_text().strip() for page in doc):
                raise ValueError(f"PDF must be readable and text-bearing: {path.name}")
            pages = len(doc)
        result.append({"file": path.relative_to(root).as_posix(), "sha256": sha256(raw).hexdigest(),
            "size_bytes": len(raw), "page_count": pages, "document_type": TYPES.get(path.name[:2], "OTHER")})
    return root, result, {"file": "manifest_pdf.txt", "handling": "READ_AS_CONTROL_MANIFEST",
                         "sha256": sha256(manifests[0].read_bytes()).hexdigest(), "listed_pdfs": len(listed)}


class PositiveCaseBot:
    def __init__(self, base_url, dataset, output, *, timeout=300, client=None, sleep=time.sleep):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
            raise ValueError("This runner is restricted to the local server")
        self.base = base_url.rstrip("/")
        self.dataset, self.output, self.timeout = Path(dataset), Path(output), timeout
        self.client = client or httpx.Client(base_url=self.base, timeout=30)
        self.sleep = sleep
        self.run_id = uuid4().hex
        self.report = {"run_id": self.run_id, "started_at": utc(), "base_url": self.base,
            "scenario": "POSITIVE_CLEAN", "expected": "No material contradictions; no fabricated downstream resources",
            "status": "RUNNING", "checks": [], "requests": [], "files": []}

    def check(self, name, condition, detail=None):
        self.report["checks"].append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
        if not condition:
            raise AssertionError(name)

    def request(self, method, path, status=200, *, key=None, error=None, **kwargs):
        headers = {"X-Request-ID": f"req_positive_{self.run_id}_{len(self.report['requests'])}"}
        if key:
            headers["Idempotency-Key"] = key
        response = self.client.request(method, "/api/v1" + path, headers=headers, **kwargs)
        self.report["requests"].append({"method": method, "path": path, "status": response.status_code})
        body = response.json()
        if response.status_code != status:
            code = (body.get("error") or {}).get("code", "UNKNOWN_ERROR")
            raise AssertionError(f"{method} {path}: expected {status}, got {response.status_code} {code}")
        assert set(body) == {"success", "data", "error", "meta"}, "Noncanonical envelope"
        assert body["meta"]["api_version"] == "v1" and body["meta"]["timestamp"].endswith("Z")
        if error:
            assert body["success"] is False and body["data"] is None and body["error"]["code"] == error
        else:
            assert body["success"] is True and body["error"] is None
        return body["data"]

    def all_items(self, path):
        rows, offset = [], 0
        while True:
            data = self.request("GET", f"{path}?limit=50&offset={offset}")
            assert data["pagination"]["offset"] == offset
            rows.extend(data["items"])
            if len(rows) >= data["pagination"]["total"]:
                return rows
            assert data["items"], "Truncated pagination"
            offset += len(data["items"])

    def run(self):
        try:
            root, files, manifest = inventory(self.dataset)
            self.report.update(dataset=str(root), files=files, control_manifest=manifest)
            self.check("all_folder_files_accounted_for", bool(files), {"pdfs": len(files), "control_files": 1})
            health = self.request("GET", "/health")
            self.check("explicit_backend_demo_identity", health["demo_mode"] is True)
            case_input = {"title": "Positive corpus QA " + self.run_id[:8], "category": "IT_EQUIPMENT",
                "description": "Automated local test of the supplied synthetic positive corpus; real analysis, no seeded results.",
                "quantity": 50, "budget_ceiling_idr": 738150000, "currency": "IDR"}
            case_key = self.run_id + "-case"
            case = self.request("POST", "/cases", 201, key=case_key, json=case_input)
            case_id = case["case_id"]
            self.report["case_id"] = case_id
            self.check("case_uuid4", UUID(case_id).version == 4)
            self.check("case_replay", self.request("POST", "/cases", 201, key=case_key, json=case_input) == case)
            print(f"Created test case {case_id}", flush=True)
            prefix = f"/cases/{case_id}"
            for index, item in enumerate(files):
                raw = (root / item["file"]).read_bytes()
                assert sha256(raw).hexdigest() == item["sha256"], "Input changed during test"
                key = f"{self.run_id}-upload-{index}"
                args = {"files": {"file": (Path(item["file"]).name, raw, "application/pdf")},
                        "data": {"document_type": item["document_type"]}}
                doc = self.request("POST", prefix + "/documents", 201, key=key, **args)
                item.update(document_id=doc["document_id"], processing_status=doc["processing_status"])
                self.check("upload_" + item["file"], doc["case_id"] == case_id and doc["sha256"] == item["sha256"]
                    and doc["page_count"] == item["page_count"] and doc["processing_status"] == "COMPLETED")
                if index == 0:
                    self.check("upload_replay", self.request("POST", prefix + "/documents", 201, key=key, **args) == doc)
                print(f"Uploaded {index+1}/{len(files)}: {item['file']}", flush=True)
            self.check("persisted_document_inventory", len(self.all_items(prefix + "/documents")) == len(files))
            payload = {"document_ids": [f["document_id"] for f in files],
                "analysis_types": ["REQUIREMENT_EXTRACTION", "CONTRADICTION_DETECTION"], "force_reanalysis": False}
            analysis_key = self.run_id + "-analysis"
            accepted = self.request("POST", prefix + "/analyses", 202, key=analysis_key, json=payload)
            self.report["job_id"] = accepted["job_id"]
            deadline, delay, previous = time.monotonic() + self.timeout, 1, None
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Analysis polling deadline reached; job is preserved for inspection")
                self.sleep(delay)
                job = self.request("GET", "/jobs/" + accepted["job_id"])
                if job["status"] != previous:
                    print("Analysis: " + job["status"], flush=True)
                    previous = job["status"]
                if job["status"] in {"COMPLETED", "NEEDS_REVIEW", "FAILED"}:
                    break
                delay = min(delay * 2, 5)
            self.report["analysis"] = job
            self.check("analysis_replay", self.request("POST", prefix + "/analyses", 202, key=analysis_key, json=payload)["job_id"] == job["job_id"])
            self.check("analysis_completed", job["status"] == "COMPLETED", job.get("error") or job.get("warnings"))
            execution = job["ai_execution"]
            self.check("real_model_and_validated_evidence", bool(execution and execution["model"] and
                execution["schema_valid"] and execution["evidence_validation_passed"]), execution)
            self.check("positive_case_has_no_false_positive", job["result"]["finding_ids"] == [])
            self.check("no_persisted_findings", self.all_items(prefix + "/findings") == [])
            self.check("no_fabricated_challenges", self.all_items(prefix + "/challenges") == [])
            self.check("no_fabricated_simulations", self.all_items(prefix + "/simulations") == [])
            self.check("no_fabricated_reviews", self.all_items(prefix + "/reviews") == [])
            self.request("POST", prefix + "/reviews", 400, key=self.run_id + "-gap",
                json={"decision": "APPROVE_CASE", "decision_reason": "Positive corpus has no integrity findings.",
                      "expected_case_version": case["version"]}, error="VALIDATION_ERROR")
            self.check("v11_rejects_approve_case_and_missing_repair", True)
            audit = self.all_items(prefix + "/audit")
            self.report["audit"] = audit
            self.check("material_upload_and_analysis_audits", sum(e["event_type"] == "DOCUMENT_UPLOADED" for e in audit) == len(files)
                and any(e["event_type"] == "CASE_CREATED" for e in audit) and any(e["event_type"] == "ANALYSIS_FINISHED" for e in audit))
            self.check("no_review_audit_created_by_rejected_gap_command", not any(e["event_type"] == "REVIEW_COMPLETED" for e in audit))
            for event in audit:
                self.check("audit_shape_" + event["event_id"], UUID(event["actor"]["actor_id"]).version == 4
                    and (event["event_hash"] is None or isinstance(event["event_hash"], str)))
            refreshed = self.request("GET", "/jobs/" + job["job_id"])
            self.check("refresh_preserves_execution", refreshed == job)
            self.report["workflow"] = {"upload": "PASS", "assess": "PASS_NO_FINDINGS",
                "challenge": "NOT_APPLICABLE_NO_FINDING", "simulation": "NOT_APPLICABLE_NO_FINDING",
                "repair": "NOT_APPLICABLE_NO_FINDING", "assure": "BLOCKED_CONTRACT_G01"}
            self.report["status"] = "BLOCKED_CONTRACT_G01"
            self.report["completion_gap"] = "The positive manifest expects final approval, but v1.1 requires repair_proposal_id and has no clean-case completion command. No fabricated resources are created."
            return 2
        except Exception as error:
            self.report["status"] = "FAIL"
            self.report["failure"] = {"type": type(error).__name__, "message": str(error)}
            return 1
        finally:
            self.report["finished_at"] = utc()
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")
            print(f"Result: {self.report['status']} | report: {self.output}", flush=True)
            self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--dataset", type=Path, default=ROOT.parent / "test_data/Positive")
    parser.add_argument("--output", type=Path, default=ROOT / ".tools/qa-results/positive-case.json")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    return PositiveCaseBot(args.base_url, args.dataset, args.output, timeout=args.timeout).run()


if __name__ == "__main__":
    raise SystemExit(main())
