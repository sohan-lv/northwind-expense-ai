import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.config import settings
from backend.database import init_db, AsyncSessionLocal
from backend.api import employees, submissions, receipts, verdicts, policy_qa

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    print("Seeding employees...")
    async with AsyncSessionLocal() as db:
        from backend.seed import seed_employees
        await seed_employees(db)

    from backend.storage.r2_client import test_connection
    r2_ok = test_connection()
    print(f"R2 connection: {'OK' if r2_ok else 'FAILED'}", flush=True)

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT COUNT(*) FROM policy_chunks"))
        count = result.scalar()

    if count == 0:
        from backend.core.policy_index import index_all_policies
        await index_all_policies("data/policies")
    else:
        print("Policies already indexed, skipping")

    yield


app = FastAPI(title="Northwind Expense AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(employees.router)
app.include_router(submissions.router)
app.include_router(receipts.router)
app.include_router(verdicts.router)
app.include_router(policy_qa.router)


@app.get("/health")
async def health():
    async with AsyncSessionLocal() as db:
        emp_count = (await db.execute(text("SELECT COUNT(*) FROM employees"))).scalar()
        chunk_count = (await db.execute(text("SELECT COUNT(*) FROM policy_chunks"))).scalar()
    return {"status": "ok", "employees": emp_count, "policy_chunks": chunk_count}
