"""Integrated dev routers: Teguh business APIs, Aris simulation and Fazhima assurance."""
from fastapi import APIRouter

from app.api.routes import analyses, cases, challenges, documents, findings, jobs, repairs, simulations, reviews, audit

router = APIRouter()
for module in (cases, documents, analyses, jobs, findings, challenges, repairs, simulations, reviews, audit):
    router.include_router(module.router)
