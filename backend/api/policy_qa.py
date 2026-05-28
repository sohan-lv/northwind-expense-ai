from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.core.qa_agent import answer_policy_question

router = APIRouter(prefix="/policy-qa", tags=["policy-qa"])


class QuestionRequest(BaseModel):
    question: str


@router.post("")
async def ask_policy_question(body: QuestionRequest, db: AsyncSession = Depends(get_db)):
    result = await answer_policy_question(body.question, db)
    return result
