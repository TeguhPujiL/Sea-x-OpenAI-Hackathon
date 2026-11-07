"""Versioned fixture manifest. Existing versions must never be overwritten.

Source: user-supplied golden requirements and contract/playbook excerpt.
Negative PDF evidence corpus is intentionally excluded.
"""
from types import MappingProxyType

from app.services.simulation.engine import FixtureSource

FIXTURES = MappingProxyType({
    "synthetic-suppliers-v1": FixtureSource(
        filename="synthetic-suppliers-v1.json",
        sha256="452fe33326a14d9dccd6f44f2e5c0336243a9243949f5d33f1d9a6e7b60a945e",
    ),
})
