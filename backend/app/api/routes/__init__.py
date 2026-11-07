"""Teguh-owned routers only; teammate routers join on the integration branch."""
from fastapi import APIRouter

from app.api.routes import analyses, cases, challenges, documents, findings, jobs, repairs

router = APIRouter()
for module in (cases, documents, analyses, jobs, findings, challenges, repairs):
    router.include_router(module.router)
