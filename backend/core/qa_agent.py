import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.retrieval import get_relevant_chunks

logger = logging.getLogger(__name__)

SCOPE_CHECK_PROMPT = """You are a scope classifier for a policy Q&A system. Determine if the question is about Northwind Logistics company policies.

Answer with JSON only:
{"in_scope": true/false, "reason": "brief explanation"}

A question is IN SCOPE if it asks about:
- Travel and expense policies
- Meal, hotel, flight, or transport reimbursement rules
- Approval thresholds or processes
- Corporate card usage
- Conference attendance rules
- Gifts and entertainment policies
- International travel rules
- Employee grades and approval authority
- Any Northwind Logistics internal policy

A question is OUT OF SCOPE if it asks about:
- General knowledge not related to Northwind policies
- Personal advice
- External companies or products
- Anything not in the policy library
"""

QA_ANSWER_PROMPT = """You are a helpful policy assistant for Northwind Logistics. Answer the employee's question using only the policy excerpts provided.

Rules:
- Only use information from the provided policy excerpts
- Quote relevant policy text verbatim when possible
- If the excerpts do not contain enough information, say so clearly
- Be concise and direct
- Include document references (e.g., TEP-002 §3) when citing policy
- When citing policy, use the exact document ID shown in the excerpt header (e.g. TEP-002, TEP-013, COC-001). Never use the excerpt index number [1] [2] as the doc_id. The doc_id must always be the policy document identifier.
"""


class QAState(TypedDict):
    question: str
    in_scope: bool
    chunks: list[dict]
    answer: str
    citations: list[dict]
    refused: bool


async def check_scope(state: QAState) -> QAState:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SCOPE_CHECK_PROMPT},
                {"role": "user", "content": state["question"]},
            ],
            response_format={"type": "json_object"},
            max_tokens=100,
        )
        data = json.loads(response.choices[0].message.content)
        in_scope = bool(data.get("in_scope", False))
    except Exception as e:
        logger.error(f"Scope check failed: {e}")
        in_scope = True  # default to in-scope on error; retrieve will handle it

    return {**state, "in_scope": in_scope, "refused": not in_scope}


async def retrieve_policy(state: QAState, db: AsyncSession) -> QAState:
    try:
        chunks, _ = await get_relevant_chunks(
            receipt_category="qa",
            query_text=state["question"],
            db=db,
            top_k=6,
        )
    except Exception as e:
        logger.error(f"Q&A retrieval failed: {e}")
        chunks = []
    return {**state, "chunks": chunks}


async def generate_answer(state: QAState) -> QAState:
    chunks = state["chunks"]
    max_sim = max((c.get("similarity_score", 0.0) for c in chunks), default=0.0)

    if not chunks or max_sim < 0.40:
        return {
            **state,
            "refused": True,
            "answer": "I could not find relevant policy information to answer this question. Please consult your HR or Finance team.",
            "citations": [],
        }

    # Build policy context
    policy_ctx = "RELEVANT POLICY EXCERPTS:\n"
    for i, chunk in enumerate(chunks, 1):
        policy_ctx += f"\n[{i}] {chunk['doc_id']} {chunk['section_number']} — {chunk['section_title']}\n{chunk['content']}\n---\n"

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": QA_ANSWER_PROMPT},
                {"role": "user", "content": f"Question: {state['question']}\n\n{policy_ctx}"},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "qa_answer",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "answer": {"type": "string"},
                            "citations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "doc_id": {"type": "string"},
                                        "section": {"type": "string"},
                                        "quote": {"type": "string"},
                                    },
                                    "required": ["doc_id", "section", "quote"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["answer", "citations"],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=800,
        )
        data = json.loads(response.choices[0].message.content)
        return {
            **state,
            "answer": data.get("answer", ""),
            "citations": data.get("citations", []),
            "refused": False,
        }
    except Exception as e:
        logger.error(f"Q&A answer generation failed: {e}")
        return {
            **state,
            "refused": True,
            "answer": "Answer generation failed. Please try again.",
            "citations": [],
        }


def decline(state: QAState) -> QAState:
    return {
        **state,
        "refused": True,
        "answer": "This question is outside the Northwind Logistics policy library. I can only answer questions about company policies.",
        "citations": [],
    }


def route_after_scope(state: QAState) -> str:
    return "retrieve_policy" if state["in_scope"] else "decline"


def _build_graph():
    graph = StateGraph(QAState)
    graph.add_node("check_scope", check_scope)
    graph.add_node("decline", decline)

    # retrieve_policy and generate_answer need db — wrapped at invoke time
    graph.add_node("retrieve_policy", retrieve_policy)
    graph.add_node("generate_answer", generate_answer)

    graph.set_entry_point("check_scope")
    graph.add_conditional_edges(
        "check_scope",
        route_after_scope,
        {"retrieve_policy": "retrieve_policy", "decline": "decline"},
    )
    graph.add_edge("retrieve_policy", "generate_answer")
    graph.add_edge("generate_answer", END)
    graph.add_edge("decline", END)

    return graph.compile()


qa_graph = _build_graph()


async def answer_policy_question(
    question: str,
    db: AsyncSession,
) -> dict:
    """
    Returns: {answer: str, citations: list[dict], refused: bool}
    """
    # LangGraph nodes that need db get it via closure — inject it here
    async def _retrieve(state: QAState) -> QAState:
        return await retrieve_policy(state, db)

    # Rebuild graph with db-bound retrieve node per invocation
    graph = StateGraph(QAState)
    graph.add_node("check_scope", check_scope)
    graph.add_node("decline", decline)
    graph.add_node("retrieve_policy", _retrieve)
    graph.add_node("generate_answer", generate_answer)
    graph.set_entry_point("check_scope")
    graph.add_conditional_edges(
        "check_scope",
        route_after_scope,
        {"retrieve_policy": "retrieve_policy", "decline": "decline"},
    )
    graph.add_edge("retrieve_policy", "generate_answer")
    graph.add_edge("generate_answer", END)
    graph.add_edge("decline", END)
    compiled = graph.compile()

    result = await compiled.ainvoke({
        "question": question,
        "in_scope": False,
        "chunks": [],
        "answer": "",
        "citations": [],
        "refused": False,
    })
    return {
        "answer": result["answer"],
        "citations": result["citations"],
        "refused": result["refused"],
    }
