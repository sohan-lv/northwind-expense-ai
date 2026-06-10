# Northwind Expense AI

An AI-powered expense pre-review system for Northwind Logistics. Finance reviewers upload receipts; the system checks them against company policies and returns structured verdicts with cited policy clauses. A human reviewer always makes the final call.

**Live demo:** https://northwind-expense-ai-production.up.railway.app

<img width="1375" height="600" alt="image" src="https://github.com/user-attachments/assets/77d541f8-b900-4c8c-ae71-0dd522c31071" />
<img width="1375" height="792" alt="image" src="https://github.com/user-attachments/assets/a17fc53c-c3b5-477a-85ad-07349c805d51" />

---

## What it does

A reviewer opens the app, picks an employee, uploads receipts and gets back a verdict for each line item — compliant, flagged, or rejected — with the exact policy clause that supports it, quoted verbatim. They can override any verdict with a comment, and the full audit trail persists across restarts.

There's also a policy Q&A interface: ask anything about the expense policies and get a cited answer. Ask something outside the policy library and the system declines rather than guessing.

---

## Running locally

**Prerequisites:** Docker, an OpenAI API key, a Cloudflare R2 bucket.

```bash
git clone https://github.com/sohan-lv/northwind-expense-ai
cd northwind-expense-ai
cp .env.example .env
```

Fill in `.env`:
```
OPENAI_API_KEY=sk-...
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=northwind-expense-ai
R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/northwind
```

```bash
# Start backend + Postgres
docker-compose up --build

# Start frontend (separate terminal)
cd frontend && npm install && npm run dev
```

- Frontend: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

On first startup the system automatically seeds 5 employees and indexes all policy documents into pgvector. Subsequent restarts skip indexing (idempotent check).

---

## Architecture

```
Browser (React + Vite + Tailwind)
│
│  HTTPS REST (/api/*)
▼
FastAPI backend (Railway)
│
├── Receipt upload pipeline (per receipt):
│     Upload to R2
│       → Extract with GPT-4o vision
│       → Classify category
│       → Two-stage pgvector retrieval
│           (category filter + cross-ref resolution)
│       → Generate verdict (GPT-4o structured output)
│       → Persist verdict + recompute submission status
│
├── Policy Q&A (LangGraph agent):
│     Scope check → retrieve → answer / decline
│
└── Persistence:
      PostgreSQL + pgvector (Railway)
      Cloudflare R2 (receipt files)
```

**Tables:** `employees`, `submissions`, `receipts`, `verdicts`, `overrides` (insert-only audit log), `policy_chunks` (pgvector).

---

## Design decisions

### Chunking: section boundaries, not fixed tokens

Policy documents have numbered sections (`3.1 Meal Caps`, `4. Client Entertainment`). I chunk at section boundaries rather than every N tokens. The reason is concrete: fixed-token chunking splits the meal caps table mid-row, so the retrieval system sees `Breakfast | $25 | Lunch` without the dinner cap. That produces wrong verdicts.

The tradeoff is variable chunk size and an assumption that documents follow consistent structure. All 30 Northwind policy documents do — they share an identical template. I added a fallback to 600-token fixed chunks for any document where section boundaries aren't detected, which handles the edge case without breaking the happy path.

### Verdict pipeline: deterministic, not agentic

The verdict path is a fixed sequence: extract → retrieve → generate verdict. I considered making this a LangGraph agent that decides its own retrieval steps, but rejected it. Compliance tooling needs to be auditable — if a verdict is wrong, you need to know exactly why. An agent that varies its own reasoning steps makes that harder. The pipeline is also faster and cheaper per receipt.

LangGraph is used only for policy Q&A, where iterative tool use genuinely adds value: the agent checks scope, searches policies, follows cross-references, and decides when to decline. That's a case where the flexibility is worth it.

### Two-stage retrieval with category filtering

Every receipt is classified into a category (meal, hotel, flight, etc.) before retrieval. The pgvector query filters by `policy_category` — a meal receipt only searches meal-related chunks, never vendor onboarding or HR policies. This matters because roughly 60% of the policy library is noise (IT policies, HR procedures, legal docs). Without filtering, noise chunks pollute the top-k results and the verdict engine reasons from irrelevant context.

Stage 2 resolves cross-references automatically: if a retrieved chunk mentions `TEP-004 §3`, the system fetches that chunk and appends it to the context. This handles the common case where a policy section says "see X for the city tier list" without including the list itself.

### GPT-4o for all receipt formats

I use GPT-4o vision for PDFs and images, and GPT-4o text for plain-text receipts. One model, one API, handles all three formats. The alternative was a separate OCR pipeline (Tesseract or similar) feeding into a text model — more complexity, more failure surface, and worse results on printed receipts with unusual layouts. The tradeoff is higher cost per receipt (~$0.007 vs ~$0.001 for OCR), which I consider worth it at this scale.

PDFs are converted to images (pdf2image + poppler) before passing to the vision API. Images are resized to max 2048px to stay within GPT-4o's vision limits.

### Confidence: citation quality, not similarity score

The first version used a 0.75 cosine similarity threshold to set confidence. Every receipt came back LOW confidence because cross-domain query-to-policy similarity naturally scores 0.35–0.55. A receipt about "dinner at Franklin Barbecue" doesn't embed close to "sanctioned client entertainment involving alcohol requires..." even when the retrieval is correct.

The current approach: HIGH confidence means citations were found AND extraction was clean AND the verdict is unambiguous (compliant or rejected). MEDIUM means something is uncertain — the receipt was unclear, or the verdict is flagged. LOW means no relevant policy was found at all. The raw similarity score is still stored in the database for the evaluation harness to measure retrieval quality independently.

### Overrides are insert-only

The `overrides` table is append-only. Original AI verdicts are never modified. Every override is a new row with the reviewer's comment, timestamp, and new verdict. The submission status reflects the most recent override, but the full history is always queryable. This is non-negotiable for a compliance system — the audit trail has to be real.

### pgvector over a dedicated vector database

Single Postgres instance for both relational data and vector search. The alternative (ChromaDB or Pinecone) would have been a second service to provision, monitor, and keep in sync with the relational data. pgvector with the same SQLAlchemy ORM keeps the stack simple. At scale, adding read replicas to Postgres handles both workloads simultaneously.

### Cloudflare R2 for file storage

R2 is S3-compatible (boto3 with a custom endpoint URL). The client is an S3-compatible storage adapter, and switching to AWS S3 is a single environment variable change. I chose R2 because the client already uses Cloudflare and R2 has no egress fees, which matters when reviewers are downloading receipts to verify verdicts.

---

## Cost per submission

Based on GPT-4o pricing, for an average 6-receipt submission:

| Step | Model | Est. tokens | Cost |
|---|---|---|---|
| Extraction × 6 | GPT-4o vision | ~800 in + 200 out each | ~$0.042 |
| Verdict × 6 | GPT-4o | ~1500 in + 400 out each | ~$0.102 |
| Embeddings × 6 | text-embedding-3-small | ~50 each | ~$0.001 |
| **Total** | | | **~$0.15** |

Policy embeddings are computed once at indexing time and reused across all submissions.

At 10,000 submissions/day: ~$1,500/day in LLM costs. The main mitigation is caching verdicts for identical receipt hashes (same file content = same verdict, skip the LLM call). Repeat submissions from the same vendors could see 20–30% cache hit rates.

---

## Scaling to 10,000 submissions/day

The application is stateless — no data lives in memory between requests. Horizontal scaling requires no code changes.

| Layer | Now | At scale |
|---|---|---|
| API | Single Railway instance | Multiple FastAPI instances, load balancer |
| Processing | Synchronous per receipt | Celery + Redis job queue, async processing |
| Database | Railway Postgres | AWS RDS Postgres + read replicas, same schema |
| Vector search | pgvector on same instance | pgvector on RDS, same queries, HNSW index |
| File storage | Cloudflare R2 | AWS S3 (one env var change) |
| LLM calls | Direct OpenAI | Add Redis cache for repeated receipt hashes |

The current synchronous pipeline means the browser waits ~15 seconds per receipt during upload. At scale, the upload endpoint would return immediately with `processing_status: processing` and the UI would poll. That's a 2-hour engineering change, not an architectural rewrite.

---

## Evaluation harness

The harness in `eval/` runs end-to-end against a live API and measures four things:

```bash
python eval/harness.py \
  --input eval/expected_outcomes/sample.json \
  --base-url https://northwind-expense-ai-production.up.railway.app
```

To use the held-out test set, replace `sample.json` with your file. The input format:

```json
{
  "test_cases": [
    {
      "type": "verdict",
      "receipt_path": "path/to/receipt.pdf",
      "employee": {"name": "...", "grade": "5", "...": "..."},
      "expected_verdict": "compliant",
      "expected_doc_ids": ["TEP-002"],
      "description": "Dinner under cap"
    },
    {
      "type": "qa",
      "question": "What is the dinner cap?",
      "expected_refused": false,
      "expected_doc_ids": ["TEP-002"],
      "description": "In-scope Q&A"
    }
  ]
}
```

**Metrics and why I chose them:**

| Metric | Weight | What it measures |
|---|---|---|
| Verdict accuracy | 40% | Did the system reach the right conclusion? Primary signal. |
| Citation relevance | 25% | Did it find the right policy? A correct verdict citing the wrong doc is a retrieval failure. |
| Refusal accuracy | 20% | Did out-of-scope questions get refused? A system that answers anything is dangerous. |
| Confidence rate | 15% | How often is the system appropriately confident? LOW confidence on obvious cases signals retrieval problems. |

Results are saved to `eval/results_{timestamp}.json`.

---

## What I'd do next

**Hybrid search.** BM25 keyword matching alongside vector search would improve retrieval of specific dollar amounts and section numbers. "What is the $75 cap" is a better BM25 query than a vector query. The retrieval layer is behind an interface — swapping in a hybrid retriever is a contained change.

**Async processing.** Move receipt processing to a Celery job queue. The upload endpoint returns immediately; the UI polls for status. This is the highest-priority change for production use.

**Policy versioning.** When a policy PDF is updated, re-index only the changed document and flag any verdicts that relied on the old version for re-review. Currently re-indexing requires a manual truncate + restart.

**Confidence calibration.** Track verdict accuracy by policy category over time. If hotel receipts consistently produce wrong verdicts, that's a signal to improve hotel-specific retrieval or add more explicit hotel policy context to the verdict prompt.

**Receipt deduplication.** Hash receipt content on upload and return the cached verdict for duplicates. Reduces LLM cost and prevents double-processing of the same receipt.
