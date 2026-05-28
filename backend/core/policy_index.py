import re
import logging
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import AsyncSessionLocal
from backend.models.policy_chunk import PolicyChunk

logger = logging.getLogger(__name__)

openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

CATEGORY_MAP = {
    "TEP-001": "general_tep",
    "TEP-002": "meals",
    "TEP-003": "meals",
    "TEP-004": "accommodation",
    "TEP-005": "air_travel",
    "TEP-006": "ground_transport",
    "TEP-007": "receipts",
    "TEP-008": "per_diem",
    "TEP-009": "grades_approval",
    "TEP-010": "corporate_card",
    "TEP-012": "gifts_entertainment",
    "TEP-013": "international",
    "TEP-014": "conference",
    "SEC-301": "international",
    "COC-001": "compliance",
}

DOC_BOUNDARY_PATTERN = re.compile(r'Document:\s*([A-Z]+-\d+)\s+Version:')
DOC_ID_PATTERN = re.compile(r'Document:\s*([A-Z]+-\d+)')
# Section headers come back as ListItem or Title, never as Title-only
SECTION_PATTERN = re.compile(r'^\d+\.[\d.]*\s+\S')
SUBSECTION_LINE_PATTERN = re.compile(r'^\d+\.\d+[\d.]*\s')
CROSS_REF_PATTERN = re.compile(r'[A-Z]+-\d+\s*§[\d.]+')


# ---------------------------------------------------------------------------
# Document splitting (unchanged)
# ---------------------------------------------------------------------------

def split_into_logical_documents(elements) -> list[tuple[str, list]]:
    """
    Split Unstructured elements from a multi-policy PDF
    into separate logical documents, one per policy.
    Returns list of (doc_id, doc_elements) tuples.
    """
    documents = []
    current_doc_id = None
    current_elements = []

    for element in elements:
        text = str(element).strip()
        match = DOC_BOUNDARY_PATTERN.search(text)

        if match:
            if current_doc_id and current_elements:
                documents.append((current_doc_id, current_elements))
            current_doc_id = match.group(1)
            current_elements = [element]
        else:
            if current_doc_id:
                current_elements.append(element)

    if current_doc_id and current_elements:
        documents.append((current_doc_id, current_elements))

    return documents


def extract_doc_title(elements) -> str:
    for element in elements[:10]:
        if type(element).__name__ == "Title":
            text = str(element).strip()
            if text and not DOC_ID_PATTERN.search(text):
                return text
    return ""


# ---------------------------------------------------------------------------
# Updated chunking logic
# ---------------------------------------------------------------------------

def is_section_boundary(element) -> bool:
    text = str(element).strip()
    element_type = type(element).__name__

    if DOC_BOUNDARY_PATTERN.search(text):
        return False

    # Section headers arrive as ListItem OR Title
    if element_type in ("ListItem", "Title"):
        if SECTION_PATTERN.match(text) and len(text) < 120:
            return True

    return False


def group_table_fragments(texts: list[str]) -> tuple[str, bool]:
    """
    Detect and merge consecutive short Title/Text fragments that
    represent table rows (e.g. meal cap tables).
    Returns (final_text, has_table).
    """
    result_lines = []
    has_table = False
    i = 0

    while i < len(texts):
        text = texts[i]

        is_fragment = (
            len(text) < 60 and
            not text.endswith(".") and
            not SECTION_PATTERN.match(text) and
            not DOC_BOUNDARY_PATTERN.search(text)
        )

        if is_fragment:
            fragments = [text]
            j = i + 1
            while j < len(texts):
                next_text = texts[j]
                next_is_fragment = (
                    len(next_text) < 60 and
                    not next_text.endswith(".") and
                    not SECTION_PATTERN.match(next_text)
                )
                if next_is_fragment:
                    fragments.append(next_text)
                    j += 1
                else:
                    break

            if len(fragments) >= 3:
                result_lines.append(f"[TABLE] {' | '.join(fragments)}")
                has_table = True
                i = j
            else:
                result_lines.extend(fragments)
                i = j
        else:
            result_lines.append(text)
            i += 1

    return "\n".join(result_lines), has_table


def chunk_elements(elements) -> list:
    """
    Split document elements into chunks at section boundaries.
    Each chunk = one numbered section.
    Tables within sections are kept atomic via group_table_fragments.
    """
    chunks = []
    current_section_num = "preamble"
    current_section_title = ""
    current_texts: list[str] = []

    for element in elements:
        text = str(element).strip()
        if not text:
            continue

        # Include doc boundary text but never treat as a section split
        if DOC_BOUNDARY_PATTERN.search(text):
            current_texts.append(text)
            continue

        if is_section_boundary(element):
            # Flush current section
            if current_texts:
                content, has_table = group_table_fragments(current_texts)
                if content.strip():
                    chunks.append({
                        "section_number": current_section_num,
                        "section_title": current_section_title,
                        "content": content,
                        "has_table": has_table,
                    })
            # Start new section
            current_section_num = text.split()[0]
            current_section_title = text
            current_texts = []
        else:
            current_texts.append(text)

    # Flush last section
    if current_texts:
        content, has_table = group_table_fragments(current_texts)
        if content.strip():
            chunks.append({
                "section_number": current_section_num,
                "section_title": current_section_title,
                "content": content,
                "has_table": has_table,
            })

    return chunks


def split_large_chunk(chunk: dict) -> list:
    """Split a >3200-char chunk at subsection line boundaries."""
    lines = chunk["content"].split("\n")
    sub_chunks = []
    current_lines: list[str] = []
    current_section_num = chunk["section_number"]
    current_section_title = chunk["section_title"]

    for line in lines:
        stripped = line.strip()
        if SUBSECTION_LINE_PATTERN.match(stripped) and current_lines:
            content = "\n".join(current_lines)
            if len(content) > 60:
                sub_chunks.append({
                    "section_number": current_section_num,
                    "section_title": current_section_title,
                    "content": content,
                    "has_table": "[TABLE]" in content,
                })
                current_lines = []
            current_section_num = stripped.split()[0]
            current_section_title = stripped
        current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines)
        sub_chunks.append({
            "section_number": current_section_num,
            "section_title": current_section_title,
            "content": content,
            "has_table": "[TABLE]" in content,
        })

    return sub_chunks if sub_chunks else [chunk]


def fixed_token_chunks(elements, max_tokens: int = 600) -> list:
    """Fallback when fewer than 2 section boundaries are detected."""
    all_texts = [str(e).strip() for e in elements if str(e).strip()]

    chunks = []
    current_texts: list[str] = []
    current_chars = 0
    max_chars = max_tokens * 4

    for text in all_texts:
        if current_chars + len(text) > max_chars and current_texts:
            content, has_table = group_table_fragments(current_texts)
            if content.strip():
                chunks.append({
                    "section_number": f"chunk_{len(chunks)}",
                    "section_title": "",
                    "content": content,
                    "has_table": has_table,
                })
            current_texts = []
            current_chars = 0

        current_texts.append(text)
        current_chars += len(text)

    if current_texts:
        content, has_table = group_table_fragments(current_texts)
        if content.strip():
            chunks.append({
                "section_number": f"chunk_{len(chunks)}",
                "section_title": "",
                "content": content,
                "has_table": has_table,
            })

    return chunks


def post_process_chunks(chunks: list) -> list:
    """Split oversized chunks; merge undersized chunks forward."""
    # Split large chunks (never split table chunks)
    expanded = []
    for chunk in chunks:
        if len(chunk["content"]) > 3200 and not chunk["has_table"]:
            expanded.extend(split_large_chunk(chunk))
        else:
            expanded.append(chunk)

    # Merge small chunks into next
    merged = []
    i = 0
    while i < len(expanded):
        chunk = expanded[i]
        if len(chunk["content"]) < 60 and i + 1 < len(expanded):
            next_chunk = expanded[i + 1]
            expanded[i + 1] = {
                "section_number": chunk["section_number"],
                "section_title": chunk["section_title"],
                "content": chunk["content"] + "\n" + next_chunk["content"],
                "has_table": chunk["has_table"] or next_chunk["has_table"],
            }
        else:
            merged.append(chunk)
        i += 1

    return merged


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=[t[:8000] for t in texts],
    )
    return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

async def index_logical_document(
    doc_id: str, doc_elements: list, db: AsyncSession
) -> int:
    # Idempotency check
    existing = await db.execute(
        select(PolicyChunk).where(PolicyChunk.doc_id == doc_id).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        print(f"Skipping {doc_id} — already indexed")
        return 0

    category = CATEGORY_MAP.get(doc_id, "unrelated")
    is_noise = category == "unrelated"
    doc_title = extract_doc_title(doc_elements)

    raw_chunks = chunk_elements(doc_elements)
    section_boundaries = sum(
        1 for c in raw_chunks if c["section_number"] != "preamble"
    )

    if section_boundaries < 2:
        chunks = fixed_token_chunks(doc_elements, max_tokens=600)
    else:
        chunks = post_process_chunks(raw_chunks)

    chunk_texts: list[str] = []
    valid_chunks: list[dict] = []

    for chunk in chunks:
        content = chunk["content"].strip()
        if len(content) < 10:
            continue
        title = chunk["section_title"]
        embed_input = f"{title}\n{content}".strip() if title else content
        chunk_texts.append(embed_input)
        valid_chunks.append(chunk)

    if not valid_chunks:
        return 0

    embeddings = await embed_texts(chunk_texts)

    for chunk, embedding in zip(valid_chunks, embeddings):
        content = chunk["content"].strip()
        cross_refs = CROSS_REF_PATTERN.findall(content)
        db.add(PolicyChunk(
            doc_id=doc_id,
            doc_title=doc_title,
            section_number=chunk["section_number"],
            section_title=chunk["section_title"],
            policy_category=category,
            content=content,
            cross_refs=cross_refs,
            is_table=chunk["has_table"],
            is_noise=is_noise,
            embedding=embedding,
        ))

    await db.commit()
    print(f"Indexing {doc_id}... done ({len(valid_chunks)} chunks)", flush=True)
    return len(valid_chunks)


async def index_all_policies(policies_dir: str) -> None:
    from unstructured.partition.pdf import partition_pdf

    pdf_files = sorted(Path(policies_dir).glob("*.pdf"))
    total_docs = 0
    total_chunks = 0

    async with AsyncSessionLocal() as db:
        for pdf_path in pdf_files:
            try:
                elements = partition_pdf(
                    filename=str(pdf_path),
                    strategy="fast",
                    infer_table_structure=True,
                )
            except Exception as exc:
                logger.error(f"Failed to parse {pdf_path.name}: {exc}")
                continue

            if not elements:
                continue

            logical_docs = split_into_logical_documents(elements)

            if not logical_docs:
                logger.warning(f"No document boundaries found in {pdf_path.name}")
                continue

            for doc_id, doc_elements in logical_docs:
                count = await index_logical_document(doc_id, doc_elements, db)
                if count > 0:
                    total_docs += 1
                    total_chunks += count

    print(f"Indexed {total_docs} documents, {total_chunks} total chunks", flush=True)


if __name__ == "__main__":
    import asyncio
    import sys

    policies_dir = sys.argv[1] if len(sys.argv) > 1 else "data/policies"
    asyncio.run(index_all_policies(policies_dir))
