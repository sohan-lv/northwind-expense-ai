# Northwind Expense AI

AI-powered expense pre-review system for Northwind Logistics. Finance reviewers upload receipts; the system checks them against company travel & expense policies and returns structured verdicts with cited policy clauses. Human reviewer always makes the final call.

---

## Live Demo

The system is deployed on Railway. Access the live UI at the Railway-provided URL.

- **Frontend**: React + Vite + Tailwind (Railway static deployment)
- **Backend API**: FastAPI on Railway (auto-deployed from `Dockerfile`)
- **Database**: PostgreSQL + pgvector on Railway
- **File Storage**: Cloudflare R2

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node 18+
- Docker (optional — for local Postgres + pgvector)

### Backend

```bash
# Clone and install
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in: DATABASE_URL, OPENAI_API_KEY, R2_* credentials

# Start the API
uvicorn backend.main:app --reload --port 8000
```

On first startup, `backend/seed.py` runs automatically and:
1. Runs `alembic upgrade head` to apply schema migrations
2. Seeds 5 employees with trip context
3. Indexes all 8 policy PDFs into pgvector (387 chunks, 16 documents)

### Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Docker Compose (local Postgres + app)

```bash
docker-compose up --build
```

---

## Architecture

```
Receipt PDF (upload)
       │
       ▼
 ┌─────────────────────────────────────────────────────┐
 │              FastAPI (async)                        │
 │                                                     │
 │  POST /submissions/{id}/receipts                    │
 │       │                                             │
 │       ├─ 1. Upload to Cloudflare R2                 │
 │       │                                             │
 │       ├─ 2. Extract (GPT-4o vision)                 │
 │       │      vendor, amount, category, line items   │
 │       │                                             │
 │       ├─ 3. Retrieve policy chunks (pgvector)       │
 │       │      category filter → cosine similarity    │
 │       │      + cross-reference resolution           │
 │       │                                             │
 │       └─ 4. Generate verdict (GPT-4o structured)    │
 │              compliant / flagged / rejected         │
 │              + cited_clauses with verbatim quotes   │
 └─────────────────────────────────────────────────────┘
       │
       ▼
  PostgreSQL + pgvector
  (employees, submissions, receipts, verdicts, overrides)
```

**Policy Q&A** uses a LangGraph agent with tool-calling to search all policy categories and synthesize answers. It refuses questions outside the policy library.

### Key components

| Component | File | Purpose |
|---|---|---|
| Extraction | `backend/core/extraction.py` | GPT-4o vision → structured receipt JSON |
| Retrieval | `backend/core/retrieval.py` | pgvector cosine search + cross-ref resolution |
| Verdict engine | `backend/core/verdict_engine.py` | GPT-4o structured output → verdict JSON |
| Policy indexer | `backend/core/policy_index.py` | PDF → section-boundary chunks → embeddings |
| Q&A agent | `backend/core/qa_agent.py` | LangGraph agent over policy chunks |

---

## Design Decisions & Tradeoffs

### Section-boundary chunking over fixed-token chunking

Policy documents have numbered sections (e.g., `3.1 Meal Caps`). Splitting at section boundaries keeps the semantics of each rule intact — a fixed 512-token window would split a table mid-row. The tradeoff is variable chunk size, but policy sections are short enough (<400 tokens typically) that this doesn't cause retrieval problems.

### Verdict pipeline is deterministic, not agentic

The verdict path is a fixed sequence: extract → retrieve → generate. Using LangGraph here would add latency and unpredictability with no benefit — the policy documents are finite and the retrieval step already selects the right context. LangGraph is reserved for Q&A where iterative retrieval over multiple policy categories adds real value.

### Confidence derived from citation quality, not similarity score

Raw cosine similarity between a receipt description and a policy chunk naturally scores 0.35–0.55 (different vocabulary). Using a 0.75 threshold would mark every verdict LOW. Instead:
- `HIGH`: policy citations found + extraction was clean (`extraction_confidence=HIGH`) + verdict is unambiguous (`compliant` or `rejected`)
- `MEDIUM`: citations found but receipt was unclear, or verdict is `flagged`
- `LOW`: no relevant policy found

### City tier uplift enforced in prompt, not code

Tier 1 / Tier 2 city classification is in the policy text (TEP-004 §3) and also embedded in the system prompt. Encoding it in code would create drift risk when the policy updates — the LLM reads the retrieved policy excerpt and the prompt's tier list is a safety net.

### INSERT-ONLY overrides table

Human reviewer overrides are never updated or deleted. Each override is an immutable audit record. The UI shows the most recent override, but the full history is preserved in the `overrides` table for compliance audit.

---

## Cost Per Submission

Approximate OpenAI API cost for a 5-receipt submission:

| Step | Model | Tokens (est.) | Cost |
|---|---|---|---|
| Extraction × 5 | GPT-4o (vision) | 500 in + 200 out each | ~$0.025 |
| Verdict × 5 | GPT-4o | 1800 in + 400 out each | ~$0.055 |
| Embeddings × 5 | text-embedding-3-small | 50 tokens each | ~$0.000 |
| **Total** | | | **~$0.08 / submission** |

Q&A adds ~$0.01–0.02 per question depending on retrieval rounds.

---

## Scaling to 10k Submissions/Day

At 10k submissions/day with an average of 4 receipts each = 40k LLM calls/day.

**Bottlenecks and mitigations:**

1. **LLM throughput**: GPT-4o rate limits (~10k RPM on Tier 4). Mitigation: add a job queue (Celery + Redis or Railway background workers) so receipt processing is async. The API returns immediately with `processing_status: processing` and the UI polls.

2. **Database connections**: asyncpg with connection pooling (`pool_size=20`, `max_overflow=30`). pgvector similarity search with HNSW index stays sub-10ms at this scale.

3. **R2 storage**: Cloudflare R2 has no egress fees and handles the object volume trivially.

4. **Embedding reuse**: Policy chunks are pre-embedded and cached in pgvector. Only receipt text needs embedding at query time — ~50 tokens per embedding call.

5. **Horizontal scaling**: FastAPI is stateless. Add Railway replicas behind a load balancer. Database is the only stateful component.

---

## Evaluation Harness

The harness in `eval/` runs end-to-end against a live API and scores the system on four metrics.

### Running

```bash
# With backend running at localhost:8000
python eval/harness.py \
  --input eval/expected_outcomes/sample.json \
  --base-url http://localhost:8000
```

### Metrics

| Metric | Weight | Description |
|---|---|---|
| Verdict Accuracy | 40% | Fraction of verdict cases where predicted verdict matches expected |
| Citation Relevance | 25% | Fraction where at least one expected policy doc appears in cited_clauses |
| Refusal Accuracy | 20% | Fraction of Q&A cases where refusal behavior matches expected |
| Confidence Rate | 15% | Fraction of verdict cases where confidence is not LOW |
| **Overall Score** | weighted | Weighted average of the four metrics |

Results are saved to `eval/results_{timestamp}.json`.

### Test cases (`eval/expected_outcomes/sample.json`)

| ID | Type | Description | Expected |
|---|---|---|---|
| v_01_denver_breakfast | verdict | Breakfast in Denver (Tier 2), within $25 cap | compliant |
| v_02_chicago_alinea | verdict | Alinea dinner in Chicago (Tier 2), $300+ vs $75 cap | rejected |
| v_03_austin_flight | verdict | Southwest flight to Austin, domestic air travel | compliant |
| qa_01_dinner_cap | qa | Dinner cap with high-cost city uplift | answered (TEP-002) |
| qa_02_international | qa | VP approval for international travel | answered (TEP-013) |
| qa_03_out_of_scope | qa | Remote work / home office policy | refused |

---

## What's Next

- **Batch upload UI**: drag-and-drop multiple receipts at once
- **Webhook notifications**: notify manager when a submission has flagged/rejected items
- **Policy version tracking**: re-run verdicts when a policy document is updated
- **Per-category confidence tuning**: track which policy categories produce the most LOW confidence verdicts and improve chunk quality there
- **Feedback loop**: allow reviewers to mark verdicts wrong; feed corrections back as few-shot examples
