from fastapi import APIRouter

from app.api.routes import analyses, audit, cases, challenges, documents, findings, jobs, repairs, reviews, simulations

router = APIRouter()
for module in (cases, documents, analyses, jobs, findings, challenges, simulations, repairs, reviews, audit):
    router.include_router(module.router)
