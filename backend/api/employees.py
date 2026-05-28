import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.employee import Employee

router = APIRouter(prefix="/employees", tags=["employees"])


class EmployeeCreate(BaseModel):
    employee_id: Optional[str] = None
    name: str
    grade: str
    department: Optional[str] = None
    manager: Optional[str] = None
    trip_purpose: Optional[str] = None
    trip_start: Optional[date] = None
    trip_end: Optional[date] = None


def _serialize(emp: Employee) -> dict:
    return {
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


@router.get("")
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).order_by(Employee.name))
    employees = result.scalars().all()
    return [_serialize(e) for e in employees]


@router.post("")
async def create_employee(body: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    trip_dates = None
    if body.trip_start or body.trip_end:
        trip_dates = {
            "start": body.trip_start.isoformat() if body.trip_start else None,
            "end": body.trip_end.isoformat() if body.trip_end else None,
        }
    emp = Employee(
        employee_id=body.employee_id,
        name=body.name,
        grade=body.grade,
        department=body.department,
        manager=body.manager,
        trip_purpose=body.trip_purpose,
        trip_dates=trip_dates,
        is_seeded=False,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return _serialize(emp)


@router.get("/{employee_id}")
async def get_employee(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = result.scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return _serialize(emp)
