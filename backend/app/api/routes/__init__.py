from fastapi import APIRouter

from app.api.routes import cases, documents, analyses, jobs, findings, challenges, simulations, repairs, reviews, audit

router = APIRouter()
for module in (cases, documents, analyses, jobs, findings, challenges, simulations, repairs, reviews, audit):
    router.include_router(module.router)
