import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from backend.config import settings


engine = create_async_engine(settings.DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    import backend.models  # noqa: F401 — registers all models with Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def recompute_submission_status(submission_id: uuid.UUID, db: AsyncSession) -> str:
    from backend.models.submission import Submission
    from backend.models.receipt import Receipt
    from backend.models.verdict import Verdict
    from backend.models.override import Override

    # Load all receipts for the submission
    receipt_rows = await db.execute(
        select(Receipt).where(Receipt.submission_id == submission_id)
    )
    receipts = receipt_rows.scalars().all()

    if not receipts:
        status = "pending"
    else:
        effective_verdicts = []
        for receipt in receipts:
            verdict_row = await db.execute(
                select(Verdict).where(Verdict.receipt_id == receipt.id)
            )
            verdict = verdict_row.scalar_one_or_none()
            if verdict is None:
                effective_verdicts.append("pending")
                continue

            # Latest override takes precedence over original verdict
            override_row = await db.execute(
                select(Override)
                .where(Override.verdict_id == verdict.id)
                .order_by(Override.overridden_at.desc())
            )
            override = override_row.scalars().first()
            effective_verdicts.append(override.new_verdict if override else verdict.verdict)

        if any(v == "rejected" for v in effective_verdicts):
            status = "rejected"
        elif any(v == "flagged" for v in effective_verdicts):
            status = "flagged"
        elif all(v == "compliant" for v in effective_verdicts):
            status = "compliant"
        else:
            status = "pending"

    # Persist the recomputed status
    submission_row = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = submission_row.scalar_one()
    submission.status = status
    await db.commit()
    return status
