"""Repeatable local Positive + Negative + mixed-corpus QA with JSON/HTML reports.

Real API/provider calls; no fabricated findings and no automatic generation retry.
Exit 0: passed; 1: failed; 2: passed checks with documented gaps/warnings.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import time
from uuid import UUID, uuid4

import httpx
import pymupdf

if __package__:
    from .positive_case_bot import PositiveCaseBot, inventory, utc, ROOT
    from .qa_report import write_html_report
else:
    from positive_case_bot import PositiveCaseBot, inventory, utc, ROOT
    from qa_report import write_html_report


SCENARIOS = ("positive", "negative", "mixed")
STEPS = ("upload", "assess", "challenge", "simulation", "repair", "assure")
RISKS = (
    ("memory_baseline_conflict", ("02_",), r"\b(?:ram|memory|16\s*gb|32\s*gb)\b"),
    ("hps_arithmetic_mismatch", ("03_",), r"\b(?:hps|arithmetic|estimate|subtotal|recomput|15[,.]?000[,.]?000)"),
    ("warranty_record_contradiction", ("06C_", "07_"), r"\bwarrant"),
    ("draft_order_deviation", ("09_",), r"\b(?:deliver|memory|order|deviat|45\s*(?:calendar|days)|16\s*gb)"),
)


def corpora(positive: Path, negative: Path):
    roots, entries, manifests = {}, [], {}
    for source, folder in (("Positive", positive), ("Negative", negative)):
        root, files, manifest = inventory(folder)
        roots[source] = root
        manifests[source] = manifest
        for item in files:
            entries.append({**item, "source": source,
                "upload_filename": source + "__" + Path(item["file"]).name})
    if len({item["upload_filename"] for item in entries}) != len(entries):
        raise ValueError("Duplicate upload names within a source folder; use distinct basenames")
    return roots, entries, manifests


def risk_coverage(findings, files):
    """Heuristic coverage candidates, never a semantic correctness verdict.

    Require real negative-source citations, not only a scenario-manifest summary.
    The report exposes every match for QA review instead of inventing findings.
    """
    by_id = {item["document_id"]: item for item in files if item.get("document_id")}
    result = []
    for name, prefixes, pattern in RISKS:
        matched = []
        for finding in findings:
            refs = finding.get("evidence", [])
            negative = [by_id[ref["document_id"]]["file"] for ref in refs
                if ref.get("document_id") in by_id and by_id[ref["document_id"]]["source"] == "Negative"]
            text = " ".join([finding.get("title", ""), finding.get("summary", ""),
                             *(ref.get("excerpt", "") for ref in refs)])
            if all(any(Path(file).name.startswith(prefix) for file in negative) for prefix in prefixes) and re.search(pattern, text, re.I):
                matched.append(finding["finding_id"])
        result.append({"name": name, "status": "PASS" if matched else "WARN", "finding_ids": matched,
            "detail": "Heuristic source/keyword match; inspect citations for semantic correctness." if matched
                else "No source-grounded candidate matched this expected risk; manual QA review required."})
    return result


class RiskCaseBot(PositiveCaseBot):
    def __init__(self, base_url, roots, files, output, *, scenario, timeout=600,
                 analysis_only=False, strict_risks=False, client=None, sleep=time.sleep):
        super().__init__(base_url, roots["Negative"], output, timeout=timeout,
            client=client or httpx.Client(base_url=base_url.rstrip("/"), timeout=120, follow_redirects=False), sleep=sleep)
        self.roots, self.files = roots, [dict(item) for item in files]
        self.analysis_only, self.strict_risks = analysis_only, strict_risks
        self.report.update(scenario=scenario.upper(), files=self.files,
            expected="Evidence-grounded negative risks remain ACTION_REQUIRED; no automatic approval",
            workflow={step: "NOT_RUN" for step in STEPS}, warnings=[], findings=[])
        self.page_text = {}
        self.stage = "upload"

    def validate_findings(self, findings, job):
        ids = [finding["finding_id"] for finding in findings]
        self.check("finding_ids_match_job", len(ids) == len(set(ids)) and set(ids) == set(job["result"]["finding_ids"]))
        self.check("negative_risks_detected", bool(findings))
        for finding in findings:
            self.check("finding_case_" + finding["finding_id"], finding["case_id"] == self.report["case_id"]
                and finding["analysis_job_id"] == job["job_id"] and UUID(finding["finding_id"]).version == 4)
            refs = finding["evidence"]
            self.check("finding_has_evidence_" + finding["finding_id"], bool(refs))
            for index, ref in enumerate(refs):
                text = self.page_text.get((ref["document_id"], ref["page_number"]))
                excerpt = " ".join(ref["excerpt"].split())
                self.check(f"evidence_{finding['finding_id']}_{index}", text is not None and bool(excerpt)
                    and excerpt in text, {"document_id": ref["document_id"], "page_number": ref["page_number"]})
        self.report["risk_coverage"] = risk_coverage(findings, self.files)
        missing = [item["name"] for item in self.report["risk_coverage"] if item["status"] != "PASS"]
        if missing:
            self.report["warnings"].append("Expected risk coverage needs manual review: " + ", ".join(missing))

    def downstream(self, prefix, findings):
        candidates = [finding for finding in findings if finding["evidence_status"] == "VERIFIED"
            and all(ref["verification_status"] == "VERIFIED" for ref in finding["evidence"])
            and any(item["source"] == "Negative" and item.get("document_id") == ref["document_id"]
                for ref in finding["evidence"] for item in self.files)]
        self.check("verified_negative_finding_for_workflow", bool(candidates))
        memory = self.report["risk_coverage"][0]["finding_ids"]
        finding = next((value for value in candidates if value["finding_id"] in memory), candidates[0])
        fid = finding["finding_id"]
        self.report["selected_finding_id"] = fid
        self.stage = "challenge"
        challenge = self.request("POST", prefix + "/challenges", 201,
            json={"finding_id": fid, "generation_mode": "AI_ASSISTED",
                  "requested_evidence": ["TECHNICAL_JUSTIFICATION", "MARKET_COMPARISON"]})
        self.report["challenge"] = challenge
        self.check("challenge_linkage", challenge["case_id"] == self.report["case_id"]
            and challenge["finding_id"] == fid and challenge["status"] == "DRAFT" and bool(challenge["ai_execution_id"]))
        self.report["workflow"][self.stage] = "PASS_DRAFT_REQUIRES_HUMAN_READINESS"

        self.stage = "simulation"
        payload = {"finding_id": fid, "baseline": {"minimum_ram_gb": 32},
            "alternative": {"minimum_ram_gb": 16}, "supplier_data_version": "synthetic-suppliers-v1"}
        key = self.run_id + "-simulation"
        simulation = self.request("POST", prefix + "/simulations", 201, key=key, json=payload)
        self.report["simulation"] = simulation
        expected = {"baseline": {"eligible_supplier_count": 1, "lowest_total_offer_idr": 825000000},
            "alternative": {"eligible_supplier_count": 3, "lowest_total_offer_idr": 660000000},
            "delta": {"eligible_supplier_count": 2, "lowest_total_offer_idr": -165000000}}
        self.check("separate_contract_simulation_fixture", simulation["case_id"] == self.report["case_id"]
            and simulation["finding_id"] == fid and simulation["result"] == expected)
        self.check("simulation_replay", self.request("POST", prefix + "/simulations", 201, key=key, json=payload) == simulation)
        self.report["workflow"][self.stage] = "PASS_CONTRACT_FIXTURE_ONLY"
        self.report["simulation_limit"] = "synthetic-suppliers-v1 is independent of both PDF packs; its delta is not actual savings or loss."

        self.stage = "repair"
        payload = {"action_type": "REQUEST_MORE_EVIDENCE", "simulation_id": simulation["simulation_id"], "generation_mode": "AI_ASSISTED"}
        path = f"/findings/{fid}/repair-proposals"
        key = self.run_id + "-repair"
        repair = self.request("POST", path, 201, key=key, json=payload)
        self.report["repair"] = repair
        self.check("repair_draft_linkage", repair["case_id"] == self.report["case_id"]
            and repair["finding_id"] == fid and repair["simulation_id"] == simulation["simulation_id"] and repair["status"] == "DRAFT")
        self.check("repair_replay", self.request("POST", path, 201, key=key, json=payload) == repair)
        repair_path = "/repair-proposals/" + repair["repair_proposal_id"]
        submitted = self.request("PATCH", repair_path, json={"status": "SUBMITTED", "expected_version": repair["version"]})
        self.report["repair"] = submitted
        self.check("repair_submission_freezes_content", submitted["status"] == "SUBMITTED"
            and submitted["proposed_text"] == repair["proposed_text"] and submitted["version"] == repair["version"] + 1)
        self.request("PATCH", repair_path, 409, error="VERSION_CONFLICT",
            json={"status": "SUBMITTED", "expected_version": repair["version"]})
        self.check("stale_repair_version_rejected", True)
        self.report["workflow"][self.stage] = "PASS_SUBMITTED_TEST_DRAFT"

        self.stage = "assure"
        case = self.request("GET", prefix)
        payload = {"repair_proposal_id": submitted["repair_proposal_id"], "decision": "REQUEST_EVIDENCE",
            "decision_reason": "Automated QA test requests supporting evidence for unresolved source contradictions; this is not procurement approval.",
            "expected_case_version": case["version"]}
        self.request("POST", prefix + "/reviews", 409, key=self.run_id + "-stale-review", error="VERSION_CONFLICT",
            json={**payload, "expected_case_version": case["version"] - 1})
        self.check("stale_case_version_rejected", True)
        key = self.run_id + "-review"
        review = self.request("POST", prefix + "/reviews", 201, key=key, json=payload)
        self.report["review"] = review
        self.check("review_completed_action_required", review["decision"] == "REQUEST_EVIDENCE"
            and review["review_status"] == "COMPLETED" and review["assurance_status_after"] == "ACTION_REQUIRED"
            and UUID(review["reviewer"]["actor_id"]).version == 4)
        self.check("review_replay", self.request("POST", prefix + "/reviews", 201, key=key, json=payload) == review)
        self.check("immutable_review_refresh", self.request("GET", "/reviews/" + review["review_id"]) == review)
        self.check("submitted_repair_unchanged", self.request("GET", repair_path) == submitted)
        self.check("server_assurance_remains_action_required", self.request("GET", prefix)["assurance_status"] == "ACTION_REQUIRED")
        self.report["workflow"][self.stage] = "PASS_REQUEST_EVIDENCE_ACTION_REQUIRED"

    def run(self):
        try:
            self.authenticate()
            self.check("explicit_backend_demo_identity", self.request("GET", "/health")["demo_mode"] is True)
            payload = {"title": self.report["scenario"].title() + " corpus QA " + self.run_id[:8], "category": "IT_EQUIPMENT",
                "description": "Isolated automated QA corpus; source packs retain their identity. No source is assumed authoritative and no procurement approval is issued.",
                "quantity": 50, "budget_ceiling_idr": 858600000, "currency": "IDR"}
            key = self.run_id + "-case"
            case = self.request("POST", "/cases", 201, key=key, json=payload)
            self.report["case_id"] = case["case_id"]
            prefix = "/cases/" + case["case_id"]
            self.check("case_replay", self.request("POST", "/cases", 201, key=key, json=payload) == case)
            print(f"{self.report['scenario']}: case {case['case_id']}", flush=True)
            for index, item in enumerate(self.files):
                raw = (self.roots[item["source"]] / item["file"]).read_bytes()
                self.check("input_unchanged_" + str(index), sha256(raw).hexdigest() == item["sha256"])
                args = {"files": {"file": (item["upload_filename"], raw, "application/pdf")}, "data": {"document_type": item["document_type"]}}
                key = f"{self.run_id}-upload-{index}"
                doc = self.request("POST", prefix + "/documents", 201, key=key, **args)
                item["document_id"] = doc["document_id"]
                self.check("upload_" + str(index), doc["case_id"] == case["case_id"] and doc["sha256"] == item["sha256"]
                    and doc["page_count"] == item["page_count"] and doc["processing_status"] == "COMPLETED")
                with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                    for number, page in enumerate(pdf, 1):
                        self.page_text[(doc["document_id"], number)] = " ".join(page.get_text().split())
                if index == 0:
                    self.check("upload_replay", self.request("POST", prefix + "/documents", 201, key=key, **args) == doc)
                print(f"{self.report['scenario']}: uploaded {index+1}/{len(self.files)} {item['upload_filename']}", flush=True)
            docs = self.all_items(prefix + "/documents")
            self.check("persisted_document_inventory", {d["document_id"] for d in docs} == {item["document_id"] for item in self.files}
                and len(docs) == len(self.files))
            self.report["workflow"][self.stage] = "PASS"
            self.stage = "assess"
            payload = {"document_ids": [item["document_id"] for item in self.files],
                "analysis_types": ["REQUIREMENT_EXTRACTION", "CONTRADICTION_DETECTION"], "force_reanalysis": False}
            key = self.run_id + "-analysis"
            accepted = self.request("POST", prefix + "/analyses", 202, key=key, json=payload)
            self.report["job_id"] = accepted["job_id"]
            deadline, delay = time.monotonic() + self.timeout, 1
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Analysis deadline reached; job preserved for inspection")
                self.sleep(delay)
                job = self.request("GET", "/jobs/" + accepted["job_id"])
                self.report["analysis"] = job
                if job["status"] in {"COMPLETED", "NEEDS_REVIEW", "FAILED"}:
                    break
                delay = min(delay * 2, 5)
            self.check("analysis_replay", self.request("POST", prefix + "/analyses", 202, key=key, json=payload)["job_id"] == job["job_id"])
            self.check("usable_analysis_result", job["status"] in {"COMPLETED", "NEEDS_REVIEW"} and job["result"] is not None,
                job.get("error") or job.get("warnings"))
            execution = job["ai_execution"]
            self.check("actual_runtime_model_and_schema", bool(execution and execution["model"] and execution["schema_valid"]))
            if job["status"] == "NEEDS_REVIEW" or job["warnings"] or not execution["evidence_validation_passed"]:
                self.report["warnings"].append("Analysis evidence quality requires human review; processing status is separate from risk severity.")
            findings = self.all_items(prefix + "/findings")
            self.report["findings"] = findings
            self.validate_findings(findings, job)
            self.report["workflow"][self.stage] = "PASS_RISKS_DETECTED"
            if not self.analysis_only:
                self.downstream(prefix, findings)
            else:
                for step in STEPS[2:]:
                    self.report["workflow"][step] = "NOT_RUN_ANALYSIS_ONLY"
            self.check("refresh_preserves_analysis", self.request("GET", "/jobs/" + job["job_id"]) == job)
            self.check("source_documents_preserved", self.all_items(prefix + "/documents") == docs)
            if self.strict_risks:
                self.stage = "risk_coverage"
                self.check("all_expected_risks_have_coverage_candidates", all(item["status"] == "PASS" for item in self.report["risk_coverage"]))
            self.report["status"] = "PASS_WITH_WARNINGS" if self.report["warnings"] else "PASS"
        except Exception as error:
            self.report["status"] = "FAIL"
            if self.stage in self.report["workflow"]:
                self.report["workflow"][self.stage] = "FAIL"
            self.report["failure"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            self.capture_audit()
            self.report["finished_at"] = utc()
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")
            self.client.close()
            print(f"{self.report['scenario']}: {self.report['status']} | {self.output}", flush=True)
        return 1 if self.report["status"] == "FAIL" else 2 if self.report["status"] == "PASS_WITH_WARNINGS" else 0

    def capture_audit(self):
        if not self.report.get("case_id"):
            return
        try:
            case_id = self.report["case_id"]
            audit = self.all_items(f"/cases/{case_id}/audit")
            self.report["audit"] = audit
            uploaded = {item["document_id"] for item in self.files if item.get("document_id")}
            self.check("audit_for_each_uploaded_document", {e["resource"]["id"] for e in audit if e["event_type"] == "DOCUMENT_UPLOADED"} == uploaded)
            expected = {"CASE_CREATED"}
            for key, event in (("analysis", "ANALYSIS_FINISHED"), ("challenge", "CHALLENGE_CREATED"),
                               ("simulation", "SIMULATION_CREATED"), ("repair", "REPAIR_CREATED"), ("review", "REVIEW_COMPLETED")):
                if self.report.get(key) and (key != "analysis" or self.report[key]["status"] in {"COMPLETED", "NEEDS_REVIEW", "FAILED"}):
                    expected.add(event)
            self.check("material_workflow_audits", expected.issubset({e["event_type"] for e in audit}))
            self.check("audit_case_actor_timestamp_and_resource", all(e["case_id"] == case_id and UUID(e["actor"]["actor_id"]).version == 4
                and e["occurred_at"].endswith("Z") and e["request_id"] and e["resource"]["version"] >= 1 for e in audit))
            self.report["audit_limit"] = "G14: null hashes are readable but no chain verification or tamper-proof claim is made. Audit presence alone does not prove rollback atomicity."
        except Exception as error:
            self.report["audit_failure"] = {"type": type(error).__name__, "message": str(error)}
            self.report["status"] = "FAIL"


def run_suite(args):
    started = utc()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = args.output_dir.resolve() / run_id
    report = {"run_id": run_id, "started_at": started, "base_url": args.base_url,
        "status": "RUNNING", "scenarios": [], "mode": "DRY_RUN" if args.dry_run else "LIVE",
        "limits": ["G01: clean-case final completion requires an approved contract addendum.",
            "G14: audit hashes may be null; hash-chain integrity is not certified.",
            "Risk coverage uses source/keyword candidates; semantic correctness needs QA review.",
            "Live refresh is checked; this bot does not restart the server or prove transaction rollback atomicity."]}
    exit_code = 1
    try:
        # Validate the destination even in dry-run mode; never ship local files to a remote host.
        validator = PositiveCaseBot(args.base_url, args.positive, output / "unused.json")
        validator.client.close()
        roots, files, manifests = corpora(args.positive, args.negative)
        report["datasets"] = {source: {"path": str(root), "manifest": manifests[source],
            "pdf_count": sum(item["source"] == source for item in files)} for source, root in roots.items()}
        for scenario in args.scenarios:
            selected = [dict(item) for item in files if scenario == "mixed" or item["source"].lower() == scenario]
            if args.dry_run:
                report["scenarios"].append({"scenario": scenario.upper(), "status": "NOT_RUN_DRY_RUN", "files": selected,
                    "checks": [{"name": "complete_manifest_inventory", "status": "PASS", "detail": {"pdfs": len(selected)}}],
                    "workflow": {step: "NOT_RUN_DRY_RUN" for step in STEPS}})
                continue
            if scenario == "positive":
                bot = PositiveCaseBot(args.base_url, roots["Positive"], output / "positive.json", timeout=args.timeout)
                bot.run()
                for item in bot.report["files"]:
                    item["source"] = "Positive"
            else:
                bot = RiskCaseBot(args.base_url, roots, selected, output / (scenario + ".json"), scenario=scenario,
                    timeout=args.timeout, analysis_only=args.analysis_only, strict_risks=args.strict_risks)
                bot.run()
            report["scenarios"].append(bot.report)
        statuses = [item["status"] for item in report["scenarios"]]
        if "FAIL" in statuses:
            report["status"], exit_code = "FAIL", 1
        elif args.dry_run:
            report["status"], exit_code = "DRY_RUN_READY", 0
        elif any(status in {"BLOCKED_CONTRACT_G01", "PASS_WITH_WARNINGS"} for status in statuses):
            report["status"], exit_code = "PASS_WITH_KNOWN_GAPS_OR_WARNINGS", 2
        else:
            report["status"], exit_code = "PASS", 0
    except Exception as error:
        report["status"] = "FAIL"
        report["failure"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["finished_at"] = utc()
        output.mkdir(parents=True, exist_ok=True)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        write_html_report(report, output / "report.html")
        (args.output_dir.resolve() / "latest.json").write_text(json.dumps({"run_id": run_id, "status": report["status"],
            "report_json": str(output / "report.json"), "report_html": str(output / "report.html")}, indent=2) + "\n", encoding="utf-8")
        print(f"Suite: {report['status']}\nJSON: {output / 'report.json'}\nHTML: {output / 'report.html'}", flush=True)
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--positive", type=Path, default=ROOT.parent / "test_data/Positive")
    parser.add_argument("--negative", type=Path, default=ROOT.parent / "test_data/Negative")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".tools/qa-results/mixed")
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--timeout", type=int, default=600, help="Per-analysis polling deadline in seconds")
    parser.add_argument("--analysis-only", action="store_true", help="Skip challenge/simulation/repair/review for negative and mixed cases")
    parser.add_argument("--strict-risks", action="store_true", help="Fail if any of the four heuristic negative-risk coverage checks is missing")
    parser.add_argument("--dry-run", action="store_true", help="Validate both complete inventories and generate reports without API calls")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or len(args.scenarios) != len(set(args.scenarios)):
        parser.error("Use a positive timeout and distinct scenarios")
    return run_suite(args)


if __name__ == "__main__":
    sys.exit(main())
