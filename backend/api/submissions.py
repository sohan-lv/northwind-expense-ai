import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.employee import Employee
from backend.models.submission import Submission
from backend.models.receipt import Receipt
from backend.models.verdict import Verdict
from backend.models.override import Override

router = APIRouter(prefix="/submissions", tags=["submissions"])


class SubmissionCreate(BaseModel):
    employee_id: uuid.UUID
    trip_purpose: Optional[str] = None
    trip_start: Optional[date] = None
    trip_end: Optional[date] = None


def _serialize_override(o: Override) -> dict:
    return {
        "id": str(o.id),
        "original_verdict": o.original_verdict,
        "new_verdict": o.new_verdict,
        "reviewer_comment": o.reviewer_comment,
        "overridden_at": o.overridden_at.isoformat() if o.overridden_at else None,
        "overridden_by": o.overridden_by,
    }


def _serialize_verdict(v: Verdict, override: Optional[Override]) -> dict:
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


def _serialize_receipt(r: Receipt, verdict: Optional[Verdict], override: Optional[Override]) -> dict:
    return {
        "id": str(r.id),
        "filename": r.filename,
        "file_type": r.file_type,
        "amount": float(r.amount) if r.amount is not None else None,
        "vendor": r.vendor,
        "receipt_date": r.receipt_date.isoformat() if r.receipt_date else None,
        "processing_status": r.processing_status,
        "verdict": _serialize_verdict(verdict, override) if verdict else None,
    }


@router.post("")
async def create_submission(body: SubmissionCreate, db: AsyncSession = Depends(get_db)):
    emp_result = await db.execute(select(Employee).where(Employee.id == body.employee_id))
    if emp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    sub = Submission(
        employee_id=body.employee_id,
        trip_purpose=body.trip_purpose,
        trip_start=body.trip_start,
        trip_end=body.trip_end,
        status="pending",
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return {
        "id": str(sub.id),
        "employee_id": str(sub.employee_id),
        "trip_purpose": sub.trip_purpose,
        "trip_start": sub.trip_start.isoformat() if sub.trip_start else None,
        "trip_end": sub.trip_end.isoformat() if sub.trip_end else None,
        "status": sub.status,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


@router.get("")
async def list_submissions(
    employee_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Submission).order_by(Submission.created_at.desc())
    if employee_id:
        query = query.where(Submission.employee_id == employee_id)
    if status:
        query = query.where(Submission.status == status)
    if date_from:
        query = query.where(Submission.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.where(Submission.created_at <= datetime.combine(date_to, datetime.max.time()))

    result = await db.execute(query)
    subs = result.scalars().all()

    items = []
    for sub in subs:
        emp_result = await db.execute(select(Employee).where(Employee.id == sub.employee_id))
        emp = emp_result.scalar_one_or_none()
        items.append({
            "id": str(sub.id),
            "employee_id": str(sub.employee_id),
            "employee_name": emp.name if emp else None,
            "trip_purpose": sub.trip_purpose,
            "trip_start": sub.trip_start.isoformat() if sub.trip_start else None,
            "trip_end": sub.trip_end.isoformat() if sub.trip_end else None,
            "status": sub.status,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
        })
    return items


@router.get("/{submission_id}")
async def get_submission(submission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sub_result = await db.execute(select(Submission).where(Submission.id == submission_id))
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    emp_result = await db.execute(select(Employee).where(Employee.id == sub.employee_id))
    emp = emp_result.scalar_one_or_none()

    receipt_result = await db.execute(
        select(Receipt).where(Receipt.submission_id == submission_id)
    )
    receipts = receipt_result.scalars().all()

    receipt_list = []
    for r in receipts:
        verdict_result = await db.execute(select(Verdict).where(Verdict.receipt_id == r.id))
        verdict = verdict_result.scalar_one_or_none()

        override = None
        if verdict:
            override_result = await db.execute(
                select(Override)
                .where(Override.verdict_id == verdict.id)
                .order_by(Override.overridden_at.desc())
            )
            override = override_result.scalars().first()

        receipt_list.append(_serialize_receipt(r, verdict, override))

    employee_dict = None
    if emp:
        employee_dict = {
            "id": str(emp.id),
            "employee_id": emp.employee_id,
            "name": emp.name,
            "grade": emp.grade,
            "department": emp.department,
            "manager": emp.manager,
            "trip_purpose": emp.trip_purpose,
            "trip_dates": emp.trip_dates,
            "is_seeded": emp.is_seeded,
            "created_at": emp.created_at.isoformat() if emp.created_at else None,
        }

    return {
        "id": str(sub.id),
        "employee": employee_dict,
        "trip_purpose": sub.trip_purpose,
        "trip_start": sub.trip_start.isoformat() if sub.trip_start else None,
        "trip_end": sub.trip_end.isoformat() if sub.trip_end else None,
        "status": sub.status,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "receipts": receipt_list,
    }
