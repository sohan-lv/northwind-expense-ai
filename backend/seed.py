import json
import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.employee import Employee

logger = logging.getLogger(__name__)


async def seed_employees(db: AsyncSession) -> None:
    submissions_dir = Path("data/submissions")
    employees_data = []

    for json_file in sorted(submissions_dir.glob("*/employee_info.json")):
        with open(json_file) as f:
            data = json.load(f)

        trip_dates_raw = data.get("trip_dates", "")
        trip_dates: dict = {}
        if " to " in trip_dates_raw:
            start, end = trip_dates_raw.split(" to ", 1)
            trip_dates = {"start": start.strip(), "end": end.strip()}

        employees_data.append({
            "employee_id": data["employee_id"],
            "name": data["name"],
            "grade": str(data["grade"]),
            "department": data.get("department"),
            "manager": data.get("manager_id"),
            "email": None,
            "trip_purpose": data.get("trip_purpose"),
            "trip_dates": trip_dates,
            "is_seeded": True,
        })

    if employees_data:
        stmt = pg_insert(Employee).values(employees_data)
        stmt = stmt.on_conflict_do_nothing(index_elements=["employee_id"])
        await db.execute(stmt)
        await db.commit()
        print(f"Seeded {len(employees_data)} employees")
    else:
        logger.warning("No employee_info.json files found under data/submissions/")
