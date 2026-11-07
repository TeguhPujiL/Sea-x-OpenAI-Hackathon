"""DC1 opt-in classification proposals; existing document API is unchanged."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from pydantic import UUID4
from app.core.security import Actor, require_scope, require_idempotency_key
from app.schemas.shared import Envelope
from app.schemas.classification import ClassificationRequest, ClassificationView
from app.services.documents.classification import classify

router = APIRouter(tags=["document-classification-proposed"])


@router.post('/documents/{document_id}/classifications',status_code=201,response_model=Envelope[ClassificationView])
def create(document_id: UUID4, payload: ClassificationRequest, request: Request,
           actor: Annotated[Actor,Depends(require_scope('document:write'))],
           key: Annotated[str,Depends(require_idempotency_key)]):
    return classify(request,actor,document_id,payload,key)
