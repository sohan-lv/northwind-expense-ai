# Northwind Expense AI

## What This Is
AI-powered expense pre-review system for Northwind Logistics.
Finance reviewers upload receipts; the system checks them against
company policies and returns structured verdicts with cited policy
clauses. Human reviewer always makes the final call.
Must be accessible from a live browser URL — not localhost.

---

## Tech Stack (LOCKED — never deviate)
- Backend: FastAPI (async)
- ORM: SQLAlchemy (async) with asyncpg
- Database: PostgreSQL + pgvector extension (Railway)
- File Storage: Cloudflare R2 via boto3 (S3-compatible)
- LLM: GPT-4o only
- Embeddings: text-embedding-3-small
- PDF Parsing: Unstructured (strategy="fast", infer_table_structure=True)
- Chunking: Section-boundary grouping (NOT fixed token, NOT semantic)
- Agent: LangGraph for policy Q&A ONLY
- Frontend: React + Vite + shadcn/ui + Tailwind
- Deployment: Railway

---

## Absolute Rules (apply to every file, no exceptions)
1. Verdict pipeline is a fixed deterministic sequence — never agentic
2. LangGraph is used for Q&A agent ONLY
3. overrides table is INSERT-ONLY — never update or delete rows
4. submission.status is recomputed and stored after every verdict or override save
5. Every user action maps to a REST endpoint — zero business logic in frontend
6. All LLM outputs use OpenAI structured outputs (JSON schema) — never parse free text
7. cited_clauses[].quote is required and non-nullable — enforce in schema and prompt
8. If max similarity_score < 0.75: force confidence=LOW and requires_human=True in code
9. Dockerfile must install poppler-utils via apt-get
10. R2 client must use custom endpoint_url — never default boto3 S3 config
11. Employee seeding uses ON CONFLICT DO NOTHING — idempotent

---

## Project Structure
northwind-expense-ai/
├── data/
│   ├── policies/          ← all policy PDFs flat
│   └── submissions/       ← 5 folders, each has employee_info.json + receipts/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── seed.py
│   ├── api/
│   │   ├── employees.py
│   │   ├── submissions.py
│   │   ├── receipts.py
│   │   ├── verdicts.py
│   │   └── policy_qa.py
│   ├── core/
│   │   ├── extraction.py
│   │   ├── retrieval.py
│   │   ├── verdict_engine.py
│   │   ├── policy_index.py
│   │   └── qa_agent.py
│   ├── models/
│   │   ├── employee.py
│   │   ├── submission.py
│   │   ├── receipt.py
│   │   ├── verdict.py
│   │   └── override.py
│   ├── schemas/
│   │   └── verdict_schema.py
│   └── storage/
│       └── r2_client.py
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx
│       │   ├── NewSubmission.jsx
│       │   ├── SubmissionDetail.jsx
│       │   └── PolicyQA.jsx
│       └── components/
│           ├── VerdictBadge.jsx
│           ├── ReceiptCard.jsx
│           ├── OverrideModal.jsx
│           └── CitationBlock.jsx
├── eval/
│   ├── harness.py
│   └── metrics.py
├── CLAUDE.md
├── docker-compose.yml
├── Dockerfile
└── .env.example

---

## How We Build (step by step — never skip ahead)
Step 1: Scaffold + config
Step 2: Database models
Step 3: Policy indexing pipeline
Step 4: Receipt extraction
Step 5: Verdict engine + retrieval
Step 6: FastAPI routes + seeding
Step 7: Frontend
Step 8: Eval harness + README + deploy