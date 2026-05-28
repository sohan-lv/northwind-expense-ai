import re
import logging

from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.policy_chunk import PolicyChunk

logger = logging.getLogger(__name__)

RECEIPT_TO_POLICY = {
    "meal":             ["meals", "grades_approval", "general_tep"],
    "alcohol":          ["meals", "compliance"],
    "hotel":            ["accommodation", "grades_approval", "general_tep"],
    "flight":           ["air_travel", "international", "grades_approval"],
    "ground_transport": ["ground_transport", "general_tep"],
    "conference":       ["conference", "meals", "accommodation", "grades_approval"],
    "gift":             ["gifts_entertainment", "compliance"],
    "per_diem":         ["per_diem", "international", "grades_approval"],
    "other":            ["general_tep", "grades_approval"],
    # Q&A searches all non-noise categories — no receipt-type filtering
    "qa": [
        "meals", "grades_approval", "general_tep", "accommodation",
        "air_travel", "ground_transport", "per_diem", "corporate_card",
        "gifts_entertainment", "international", "conference", "compliance",
    ],
}

CRITICAL_CROSS_REFS = {
    "TEP-004 §3":   ("TEP-004", "3."),
    "TEP-009 §3":   ("TEP-009", "3."),
    "TEP-009 §3.2": ("TEP-009", "3."),
    "TEP-002 §4":   ("TEP-002", "4."),
    "TEP-001 §4":   ("TEP-001", "4."),
    "TEP-005 §2.3": ("TEP-005", "2."),
    "TEP-003 §2.2": ("TEP-003", "2."),
    "TEP-013 §2":   ("TEP-013", "2."),
}

SIMILARITY_THRESHOLD = 0.75
LOW_CONFIDENCE_THRESHOLD = 0.75

DOLLAR_PATTERN = re.compile(r'\$[\d,.]+')


async def get_embedding(text: str) -> list[float]:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


async def fetch_chunk_by_section(
    doc_id: str,
    section_number: str,
    db: AsyncSession,
) -> dict | None:
    result = await db.execute(
        select(PolicyChunk).where(
            PolicyChunk.doc_id == doc_id,
            PolicyChunk.section_number.like(f"{section_number}%"),
        )
    )
    chunk = result.scalars().first()
    if chunk:
        return {
            "doc_id": chunk.doc_id,
            "section_number": chunk.section_number,
            "section_title": chunk.section_title,
            "content": chunk.content,
            "is_table": chunk.is_table,
            "similarity_score": 0.80,
        }
    return None


async def get_relevant_chunks(
    receipt_category: str,
    query_text: str,
    db: AsyncSession,
    top_k: int = 5,
) -> tuple[list[dict], float]:
    """
    Two-stage retrieval:
    Stage 1: Vector search filtered by policy_category
    Stage 2: Auto-fetch cross-referenced chunks

    Returns (chunks_list, max_similarity_score)
    """
    # Stage 1: filtered vector search
    query_embedding = await get_embedding(query_text)
    categories = RECEIPT_TO_POLICY.get(receipt_category, RECEIPT_TO_POLICY["other"])

    # asyncpg mis-parses :param::vector (sees :: as part of param name).
    # Using CAST(:param AS vector) keeps the bind parameter clean.
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = text("""
        SELECT
            doc_id,
            section_number,
            section_title,
            content,
            is_table,
            1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
        FROM policy_chunks
        WHERE policy_category = ANY(:categories)
        AND is_noise = false
        ORDER BY embedding <=> CAST(:query_embedding AS vector)
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
            "query_embedding": embedding_str,
            "categories": categories,
            "top_k": top_k,
        },
    )
    chunks = [dict(row._mapping) for row in result]

    # Keyword boost: if query has a dollar amount and chunk content matches, +0.05
    dollar_amounts = DOLLAR_PATTERN.findall(query_text)
    if dollar_amounts:
        for chunk in chunks:
            matched = any(amt in (chunk.get("content") or "") for amt in dollar_amounts)
            chunk["similarity_score"] = float(chunk["similarity"]) + (0.05 if matched else 0.0)
    else:
        for chunk in chunks:
            chunk["similarity_score"] = float(chunk["similarity"])

    max_similarity = max((c["similarity_score"] for c in chunks), default=0.0)

    # Stage 2: cross-reference resolution
    existing_keys = {(c["doc_id"], c["section_number"]) for c in chunks}
    for chunk in list(chunks):
        content = chunk.get("content") or ""
        for ref_key, (target_doc, target_section) in CRITICAL_CROSS_REFS.items():
            if ref_key in content:
                if (target_doc, target_section) not in existing_keys:
                    fetched = await fetch_chunk_by_section(target_doc, target_section, db)
                    if fetched:
                        chunks.append(fetched)
                        existing_keys.add((fetched["doc_id"], fetched["section_number"]))

    return chunks, max_similarity
