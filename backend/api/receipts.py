import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, recompute_submission_status
from backend.models.employee import Employee
from backend.models.override import Override
from backend.models.receipt import Receipt
from backend.models.submission import Submission
from backend.models.verdict import Verdict

logger = logging.getLogger(__name__)

router = APIRouter(tags=["receipts"])


def _serialize_override(o: Override) -> dict:
    return {
        "id": str(o.id),
        "original_verdict": o.original_verdict,
        "new_verdict": o.new_verdict,
        "reviewer_comment": o.reviewer_comment,
        "overridden_at": o.overridden_at.isoformat() if o.overridden_at else None,
        "overridden_by": o.overridden_by,
    }


def _serialize_verdict(v: Verdict, override: Override | None) -> dict:
    return {
        "id": str(v.id),
        "category": v.category,
        "verdict": v.verdict,
        "confidence": v.confidence,
        "reasoning": v.reasoning,
        "cited_clauses": v.cited_clauses,
        "requires_human_review": v.requires_human,
        "similarity_score": v.similarity_score,
        "override": _serialize_override(override) if override else None,
    }


def _serialize_receipt(r: Receipt, verdict: Verdict | None, override: Override | None) -> dict:
    return {
        "id": str(r.id),
        "submission_id": str(r.submission_id),
        "filename": r.filename,
        "file_type": r.file_type,
        "r2_key": r.r2_key,
        "amount": float(r.amount) if r.amount is not None else None,
        "vendor": r.vendor,
        "receipt_date": r.receipt_date.isoformat() if r.receipt_date else None,
        "processing_status": r.processing_status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "verdict": _serialize_verdict(verdict, override) if verdict else None,
    }


async def _save_failed_verdict(receipt: Receipt, extracted: dict, db: AsyncSession) -> Verdict:
    v = Verdict(
        receipt_id=receipt.id,
        category=extracted.get("category", "other"),
        verdict="flagged",
        confidence="LOW",
        reasoning="Processing failed. Manual review required.",
        cited_clauses=[],
        similarity_score=0.0,
        requires_human=True,
    )
    db.add(v)
    await db.commit()
    return v


@router.post("/submissions/{submission_id}/receipts")
async def upload_receipt(
    submission_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # Step 1: verify submission exists
    sub_result = await db.execute(select(Submission).where(Submission.id == submission_id))
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Step 2: read file bytes
    file_bytes = await file.read()

    # Step 3: create receipt row
    receipt = Receipt(
        submission_id=submission_id,
        filename=file.filename or "upload",
        file_type="unknown",
        processing_status="processing",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)

    extracted: dict = {}
    verdict_row: Verdict | None = None

    try:
        from backend.storage.r2_client import upload_file
        from backend.core.extraction import extract_receipt
        from backend.core.retrieval import get_relevant_chunks
        from backend.core.verdict_engine import generate_verdict

        # Step 4: upload to R2
        r2_key = f"uploads/{submission_id}/{receipt.id}/{file.filename}"
        upload_file(file_bytes, r2_key)

        # Step 5: extract receipt data
        extracted = await extract_receipt(
            file_bytes,
            file.filename or "upload",
            file.content_type or "application/octet-stream",
        )

        # Step 6: update receipt with extracted data
        receipt.file_type = extracted.get("category", "other")
        receipt.amount = extracted.get("amount")
        receipt.vendor = extracted.get("vendor")
        raw_date = extracted.get("date")
        if raw_date:
            try:
                receipt.receipt_date = date.fromisoformat(raw_date)
            except (ValueError, TypeError):
                receipt.receipt_date = None
        receipt.r2_key = r2_key
        receipt.extracted_data = extracted
        receipt.processing_status = "processed"
        await db.commit()

        # Step 7: build retrieval query
        query = (
            f"{extracted.get('category', '')} "
            f"{extracted.get('vendor', '')} "
            f"${extracted.get('amount', '')} "
            f"{extracted.get('raw_description', '')}"
        ).strip()

        # Step 8: get relevant chunks
        chunks, max_sim = await get_relevant_chunks(
            extracted.get("category", "other"),
            query,
            db,
        )

        # Step 9: get employee info
        emp_result = await db.execute(select(Employee).where(Employee.id == sub.employee_id))
        emp = emp_result.scalar_one_or_none()
        employee_dict = {}
        if emp:
            employee_dict = {
                "name": emp.name,
                "grade": emp.grade,
                "department": emp.department,
                "manager": emp.manager,
                "trip_purpose": sub.trip_purpose or emp.trip_purpose,
                "trip_dates": {
                    "start": str(sub.trip_start) if sub.trip_start else None,
                    "end": str(sub.trip_end) if sub.trip_end else None,
                },
            }

        # Step 10: generate verdict
        verdict_data = await generate_verdict(
            employee_dict,
            {"id": str(receipt.id)},
            extracted,
            chunks,
            max_sim,
            db,
        )

        # Step 11: save verdict
        verdict_row = Verdict(
            receipt_id=receipt.id,
            category=verdict_data.get("category"),
            verdict=verdict_data.get("verdict"),
            confidence=verdict_data.get("confidence"),
            reasoning=verdict_data.get("reasoning"),
            cited_clauses=verdict_data.get("cited_clauses", []),
            similarity_score=verdict_data.get("similarity_score"),
            requires_human=verdict_data.get("requires_human_review", False),
        )
        db.add(verdict_row)
        await db.commit()

    except Exception as exc:
        logger.error(f"Receipt pipeline failed for {file.filename}: {exc}")
        try:
            receipt.processing_status = "failed"
            await db.commit()
            verdict_row = await _save_failed_verdict(receipt, extracted, db)
        except Exception as inner:
            logger.error(f"Failed to save failure state: {inner}")

    # Step 12: recompute submission status
    try:
        await recompute_submission_status(submission_id, db)
    except Exception as exc:
        logger.error(f"Status recompute failed: {exc}")

    # Step 13: return receipt with verdict
    override = None
    if verdict_row:
        override_result = await db.execute(
            select(Override)
            .where(Override.verdict_id == verdict_row.id)
            .order_by(Override.overridden_at.desc())
        )
        override = override_result.scalars().first()

    return _serialize_receipt(receipt, verdict_row, override)


@router.get("/receipts/{receipt_id}")
async def get_receipt(receipt_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Receipt).where(Receipt.id == receipt_id))
    receipt = result.scalar_one_or_none()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    verdict_result = await db.execute(select(Verdict).where(Verdict.receipt_id == receipt.id))
    verdict = verdict_result.scalar_one_or_none()

    override = None
    if verdict:
        override_result = await db.execute(
            select(Override)
            .where(Override.verdict_id == verdict.id)
            .order_by(Override.overridden_at.desc())
        )
        override = override_result.scalars().first()

    return _serialize_receipt(receipt, verdict, override)
