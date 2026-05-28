import base64
import io
import json
import logging

from openai import AsyncOpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
SUPPORTED_TEXT_EXTENSIONS = {'txt', 'text', 'csv'}
MAX_IMAGE_SIZE = 2048

EXTRACTION_SYSTEM_PROMPT = """You are a receipt data extraction specialist. Extract structured data from the receipt provided.

Return ONLY a valid JSON object with exactly these fields:
{
  "vendor": "business name from receipt",
  "date": "YYYY-MM-DD format, null if not found",
  "amount": total amount as float null if not found,
  "currency": "USD unless clearly otherwise",
  "category": one of exactly these values: meal, hotel, flight, ground_transport, conference, gift, alcohol, per_diem, other,
  "line_items": [{"description": "string", "amount": float}],
  "meal_type": "breakfast or lunch or dinner or null",
  "attendee_count": integer or null,
  "vendor_address": "city and state if visible else null",
  "raw_description": "one sentence describing this receipt",
  "extraction_confidence": "HIGH or MEDIUM or LOW"
}

Rules:
- amount must be the TOTAL amount shown on the receipt
- For meal receipts look carefully for tip in the total
- If alcohol appears on a meal receipt set category to alcohol
- currency defaults to USD
- meal_type only applies when category is meal
- extraction_confidence is HIGH when vendor date and amount are all clearly visible MEDIUM when any field is inferred LOW when image is unclear or multiple key fields are missing
- Return ONLY the JSON object with no other text
"""


def detect_file_type(filename: str, content_type: str) -> str:
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    if ext == 'pdf':
        return 'pdf'
    elif ext in SUPPORTED_IMAGE_EXTENSIONS:
        return 'image'
    elif ext in SUPPORTED_TEXT_EXTENSIONS:
        return 'txt'
    elif 'pdf' in content_type:
        return 'pdf'
    elif 'image' in content_type:
        return 'image'
    else:
        return 'txt'


def pdf_to_image_bytes(file_bytes: bytes) -> bytes:
    from pdf2image import convert_from_bytes
    from PIL import Image

    pages = convert_from_bytes(file_bytes, dpi=150)
    image = pages[0]

    w, h = image.size
    longest = max(w, h)
    if longest > MAX_IMAGE_SIZE:
        scale = MAX_IMAGE_SIZE / longest
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def preprocess_image(file_bytes: bytes) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(file_bytes))

    if image.mode not in ("RGB",):
        image = image.convert("RGB")

    w, h = image.size
    longest = max(w, h)
    if longest > MAX_IMAGE_SIZE:
        scale = MAX_IMAGE_SIZE / longest
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def encode_image_b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


async def _call_gpt4o_vision(b64_image: str) -> dict:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract all receipt data and return JSON only.",
                    },
                ],
            },
        ],
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


async def _call_gpt4o_text(text_content: str) -> dict:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Receipt content:\n{text_content}"},
        ],
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


async def extract_receipt(
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/octet-stream",
) -> dict:
    try:
        file_type = detect_file_type(filename, content_type)

        if file_type == "pdf":
            image_bytes = pdf_to_image_bytes(file_bytes)
            b64 = encode_image_b64(image_bytes)
            result = await _call_gpt4o_vision(b64)
        elif file_type == "image":
            image_bytes = preprocess_image(file_bytes)
            b64 = encode_image_b64(image_bytes)
            result = await _call_gpt4o_vision(b64)
        else:
            text_content = file_bytes.decode("utf-8", errors="replace")
            result = await _call_gpt4o_text(text_content)

        # Ensure required fields are present
        result.setdefault("vendor", None)
        result.setdefault("date", None)
        result.setdefault("amount", None)
        result.setdefault("currency", "USD")
        result.setdefault("category", "other")
        result.setdefault("line_items", [])
        result.setdefault("meal_type", None)
        result.setdefault("attendee_count", None)
        result.setdefault("vendor_address", None)
        result.setdefault("raw_description", "")
        result.setdefault("extraction_confidence", "LOW")

        return result

    except Exception as e:
        logger.error(f"Extraction failed for '{filename}': {e}")
        return {
            "vendor": None,
            "date": None,
            "amount": None,
            "currency": "USD",
            "category": "other",
            "line_items": [],
            "meal_type": None,
            "attendee_count": None,
            "vendor_address": None,
            "raw_description": f"Extraction failed for {filename}",
            "extraction_confidence": "LOW",
        }
