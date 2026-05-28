import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, recompute_submission_status
from backend.models.override import Override
from backend.models.receipt import Receipt
from backend.models.verdict import Verdict

router = APIRouter(prefix="/verdicts", tags=["verdicts"])

VALID_VERDICTS = {"compliant", "flagged", "rejected"}


class OverrideCreate(BaseModel):
    new_verdict: str
    reviewer_comment: str
    overridden_by: Optional[str] = None


def _serialize_verdict(v: Verdict) -> dict:
    return {
        "id": str(v.id),
        "receipt_id": str(v.receipt_id),
        "category": v.category,
        "verdict": v.verdict,
        "confidence": v.confidence,
        "reasoning": v.reasoning,
        "cited_clauses": v.cited_clauses,
        "requires_human_review": v.requires_human,
        "similarity_score": v.similarity_score,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _serialize_override(o: Override) -> dict:
    return {
        "id": str(o.id),
        "verdict_id": str(o.verdict_id),
        "original_verdict": o.original_verdict,
        "new_verdict": o.new_verdict,
        "reviewer_comment": o.reviewer_comment,
        "overridden_at": o.overridden_at.isoformat() if o.overridden_at else None,
        "overridden_by": o.overridden_by,
    }


@router.get("/{verdict_id}")
async def get_verdict(verdict_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Verdict).where(Verdict.id == verdict_id))
    verdict = result.scalar_one_or_none()
    if verdict is None:
        raise HTTPException(status_code=404, detail="Verdict not found")

    receipt_result = await db.execute(select(Receipt).where(Receipt.id == verdict.receipt_id))
    receipt = receipt_result.scalar_one_or_none()

    return {
        **_serialize_verdict(verdict),
        "receipt": {
            "id": str(receipt.id) if receipt else None,
            "filename": receipt.filename if receipt else None,
            "amount": float(receipt.amount) if receipt and receipt.amount else None,
            "vendor": receipt.vendor if receipt else None,
        },
    }


@router.post("/{verdict_id}/override")
async def create_override(
    verdict_id: uuid.UUID,
    body: OverrideCreate,
    db: AsyncSession = Depends(get_db),
):
    # Fetch verdict
    result = await db.execute(select(Verdict).where(Verdict.id == verdict_id))
    verdict = result.scalar_one_or_none()
    if verdict is None:
        raise HTTPException(status_code=404, detail="Verdict not found")

    # Validate body
    if not body.reviewer_comment or not body.reviewer_comment.strip():
        raise HTTPException(status_code=400, detail="reviewer_comment must not be empty")
    if body.new_verdict not in VALID_VERDICTS:
        raise HTTPException(
            status_code=400,
            detail=f"new_verdict must be one of: {', '.join(sorted(VALID_VERDICTS))}",
        )

    # INSERT-ONLY — never update the verdict row
    override = Override(
        verdict_id=verdict.id,
        original_verdict=verdict.verdict,
        new_verdict=body.new_verdict,
        reviewer_comment=body.reviewer_comment.strip(),
        overridden_by=body.overridden_by,
    )
    db.add(override)
    await db.commit()
    await db.refresh(override)

    # Recompute submission status via receipt → submission chain
    receipt_result = await db.execute(select(Receipt).where(Receipt.id == verdict.receipt_id))
    receipt = receipt_result.scalar_one_or_none()
    if receipt:
        await recompute_submission_status(receipt.submission_id, db)

    return _serialize_override(override)
