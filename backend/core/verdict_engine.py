import json
import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.retrieval import LOW_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

VERDICT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "expense_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "verdict": {
                    "type": "string",
                    "enum": ["compliant", "flagged", "rejected"],
                },
                "confidence": {
                    "type": "string",
                    "enum": ["HIGH", "MEDIUM", "LOW"],
                },
                "amount": {"type": ["number", "null"]},
                "currency": {"type": "string"},
                "reasoning": {"type": "string"},
                "cited_clauses": {
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
                "requires_human_review": {"type": "boolean"},
            },
            "required": [
                "category",
                "verdict",
                "confidence",
                "amount",
                "currency",
                "reasoning",
                "cited_clauses",
                "requires_human_review",
            ],
            "additionalProperties": False,
        },
    },
}

VERDICT_SYSTEM_PROMPT = """You are a compliance reviewer for Northwind Logistics expense policy. Your job is to determine whether an expense is compliant, flagged, or rejected based on company policies.

You will be given:
1. Employee information (name, grade, department, trip context)
2. Receipt data (vendor, amount, category, line items)
3. Relevant policy excerpts

Your verdict must be one of:
- compliant: expense clearly follows all applicable policies
- flagged: expense may violate policy or needs clarification
- rejected: expense clearly violates policy

Rules for cited_clauses:
- You MUST quote verbatim text from the policy excerpts provided
- NEVER reference a section without including the actual quote
- The quote field must contain real text from the policy
- If no policy is relevant, cited_clauses must be empty array
- doc_id must be the document identifier from the excerpt header, e.g. "TEP-002" or "COC-001" — never use a number
- section must be the section number from the excerpt header, e.g. "2." or "3.1"

Rules for confidence:
- HIGH: policy is clear and directly addresses this expense
- MEDIUM: policy exists but requires interpretation
- LOW: no clear policy found or situation is ambiguous

Rules for reasoning:
- Be specific: reference the actual dollar amounts and limits
- Explain exactly why the verdict was reached
- If flagged or rejected, state what the violation is clearly

Key policies to apply:
- Meal caps: Breakfast $25, Lunch $35, Dinner $75 per person inclusive of tax and tip
- HIGH-COST CITY UPLIFT: caps increase by 25% ONLY for Tier 1 cities. Tier 2 cities use standard caps with absolutely NO uplift whatsoever.
- Tier 1 cities (25% uplift applies): New York NY, San Francisco CA, Boston MA, Washington DC, Los Angeles CA, Seattle WA, London UK, Zurich CH, Tokyo JP, Singapore SG
- Tier 2 cities (NO uplift, standard caps): Chicago IL, Denver CO, Austin TX, Atlanta GA, Dallas TX, Houston TX, Miami FL, and all others not in the Tier 1 list above
- Always check the retrieved TEP-004 §3 chunk to confirm which tier a city belongs to
- Alcohol only reimbursable during sanctioned client entertainment with VP approval and external attendees present
- Solo travel alcohol is never reimbursable
- Hotel lodging caps vary by city tier — always check the TEP-004 policy excerpt provided for the exact cap applicable to the destination city
- For hotel receipts: always calculate the per-night rate from the line items before comparing against the city tier cap. Look for room charges and divide by number of nights stayed. Compare the per-night cost against the cap, not the total bill. Example: a total of $470 for 2 nights at $215 per night plus $23 tax per night = $238 per night, which is compliant for a Tier 2 city ($250 cap) even though the total exceeds $250.
- Approval thresholds: up to $1000 manager, $1000-$5000 director, above $5000 VP
- International travel requires VP approval
- Grade 9+ = VP level
"""


def build_verdict_context(
    employee: dict,
    receipt: dict,
    extracted_data: dict,
    chunks: list[dict],
) -> str:
    employee_ctx = f"""
EMPLOYEE CONTEXT:
Name: {employee.get('name')}
Grade: {employee.get('grade')}
Department: {employee.get('department')}
Manager: {employee.get('manager')}
Trip Purpose: {employee.get('trip_purpose')}
Trip Dates: {employee.get('trip_dates')}
"""

    receipt_ctx = f"""
RECEIPT DATA:
Vendor: {extracted_data.get('vendor')}
Date: {extracted_data.get('date')}
Amount: {extracted_data.get('amount')} {extracted_data.get('currency', 'USD')}
Category: {extracted_data.get('category')}
Meal Type: {extracted_data.get('meal_type')}
Attendee Count: {extracted_data.get('attendee_count')}
Line Items: {extracted_data.get('line_items')}
Description: {extracted_data.get('raw_description')}
"""

    policy_ctx = "\nRELEVANT POLICY EXCERPTS:\n"
    for i, chunk in enumerate(chunks, 1):
        policy_ctx += f"""
=== EXCERPT {i} | doc_id={chunk['doc_id']} | section={chunk['section_number']} | {chunk['section_title']} ===
{chunk['content']}
"""

    return employee_ctx + receipt_ctx + policy_ctx


async def generate_verdict(
    employee: dict,
    receipt_db_row: dict,
    extracted_data: dict,
    chunks: list[dict],
    max_similarity: float,
    db: AsyncSession,
) -> dict:
    """
    Generate a structured verdict for a receipt.
    Always returns a valid verdict dict.
    Never raises.
    """
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        context = build_verdict_context(employee, receipt_db_row, extracted_data, chunks)

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": VERDICT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            response_format=VERDICT_SCHEMA,
            max_tokens=1500,
        )
        verdict = json.loads(response.choices[0].message.content)

        # Confidence reflects verdict quality not retrieval similarity.
        # Similarity score is stored separately for eval harness use.
        # User-facing confidence should reflect: did we find policy
        # evidence AND was the receipt clear AND is verdict definitive?
        has_citations = len(verdict.get("cited_clauses", [])) > 0
        extraction_confident = (
            extracted_data.get("extraction_confidence") == "HIGH"
        )
        verdict_value = verdict.get("verdict")

        if has_citations and extraction_confident:
            if verdict_value in ("compliant", "rejected"):
                # Clear verdict with policy evidence and clean receipt
                verdict["confidence"] = "HIGH"
                verdict["requires_human_review"] = False
            else:
                # Flagged = ambiguous by definition, needs human eye
                verdict["confidence"] = "MEDIUM"
                verdict["requires_human_review"] = True
        elif has_citations and not extraction_confident:
            # Policy found but receipt was unclear
            verdict["confidence"] = "MEDIUM"
            verdict["requires_human_review"] = False
            if verdict_value == "flagged":
                verdict["requires_human_review"] = True
        else:
            # No relevant policy found at all
            verdict["confidence"] = "LOW"
            verdict["requires_human_review"] = True

        verdict["similarity_score"] = max_similarity
        return verdict

    except Exception as e:
        logger.error(f"Verdict generation failed: {e}")
        return {
            "category": extracted_data.get("category", "other"),
            "verdict": "flagged",
            "confidence": "LOW",
            "amount": extracted_data.get("amount"),
            "currency": extracted_data.get("currency", "USD"),
            "reasoning": "Verdict generation failed. Manual review required.",
            "cited_clauses": [],
            "requires_human_review": True,
            "similarity_score": 0.0,
        }
