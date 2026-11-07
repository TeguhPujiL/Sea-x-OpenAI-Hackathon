"""Merge regression: real simulation and assurance commands on migrated SQLite."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.response import ApiError
from app.api.routes.simulations import get_simulation_access
from app.core.security import Actor, get_actor
from app.models import AuditEvent, IdempotencyRecord, Simulation
from app.services.simulation.shared_repository import PersistedSimulationAccess
from conftest import assert_envelope, post_review


def test_simulation_and_review_share_migrated_database(qa):
    actor = Actor(qa.actor_id, "Synthetic QA Reviewer", "REVIEWER",
        qa.settings.demo_scopes | {"simulation:write", "simulation:read"})
    qa.app.dependency_overrides[get_actor] = lambda: actor

    class TrustedTestPolicy:
        def require_case(self, case_id):
            if case_id not in qa.grants.get(actor.actor_id, set()):
                raise ApiError(404, "RESOURCE_NOT_FOUND", "Case not found")

        def require_finding(self, case_id, finding_id):
            self.require_case(case_id)

    access = PersistedSimulationAccess(qa.app.state.session_factory, TrustedTestPolicy())
    qa.app.dependency_overrides[get_simulation_access] = lambda: access
    payload = {"finding_id": str(qa.chain.finding.id),
        "baseline": {"minimum_ram_gb": 32}, "alternative": {"minimum_ram_gb": 16},
        "supplier_data_version": "synthetic-suppliers-v1"}
    path = f"/api/v1/cases/{qa.chain.case.id}/simulations"
    response = qa.client.post(path, json=payload, headers={"Idempotency-Key": "integrated-simulation"})
    simulation = assert_envelope(response, 201)["data"]
    assert simulation["result"]["delta"] == {
        "eligible_supplier_count": 2, "lowest_total_offer_idr": -165000000}
    assert_envelope(qa.client.get(f"/api/v1/simulations/{simulation['simulation_id']}"), 200)
    replay = qa.client.post(path, json=payload, headers={"Idempotency-Key": "integrated-simulation"})
    # Preserve simulation's documented G09 full-envelope replay policy. Its
    # original meta differs from assurance's fresh-meta policy; do not change
    # either owner's proposed replay semantics as part of this merge.
    assert replay.status_code == 201 and replay.json() == response.json()
    assert_envelope(post_review(qa), 201)
    timeline = assert_envelope(qa.client.get(qa.path.replace("/reviews", "/audit")), 200)["data"]
    assert timeline["pagination"]["total"] == 3
    assert {e["event_type"] for e in timeline["items"]} == {
        "SIMULATION_CREATED", "REVIEW_COMPLETED", "CASE_ASSURANCE_CHANGED"}
    with Session(qa.engine) as session:
        # One fixture simulation plus one computed through the merged API.
        assert session.scalar(select(func.count()).select_from(Simulation)) == 2
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 3
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 2
