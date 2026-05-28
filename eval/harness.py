"""
Evaluation harness for Northwind Expense AI.
Usage: python eval/harness.py --input eval/expected_outcomes/sample.json --base-url http://localhost:8000
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from eval.metrics import (
    compute_citation_relevance,
    compute_confidence_rate,
    compute_overall_score,
    compute_refusal_accuracy,
    compute_verdict_accuracy,
)

TIMEOUT = 120.0
PROJECT_ROOT = Path(__file__).parent.parent


def build_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def run_verdict_case(client: httpx.Client, base_url: str, case: dict) -> dict:
    emp = case["employee"]

    emp_resp = client.post(build_url(base_url, "/api/employees"), json={
        "employee_id": emp.get("employee_id"),
        "name": emp["name"],
        "grade": str(emp["grade"]),
        "department": emp.get("department"),
        "manager": emp.get("manager"),
        "trip_purpose": emp.get("trip_purpose"),
        "trip_start": emp.get("trip_start"),
        "trip_end": emp.get("trip_end"),
    })
    emp_resp.raise_for_status()
    emp_id = emp_resp.json()["id"]

    sub_resp = client.post(build_url(base_url, "/api/submissions"), json={
        "employee_id": emp_id,
        "trip_purpose": emp.get("trip_purpose"),
        "trip_start": emp.get("trip_start"),
        "trip_end": emp.get("trip_end"),
    })
    sub_resp.raise_for_status()
    sub_id = sub_resp.json()["id"]

    receipt_path = PROJECT_ROOT / case["receipt_path"]
    with open(receipt_path, "rb") as f:
        receipt_resp = client.post(
            build_url(base_url, f"/api/submissions/{sub_id}/receipts"),
            files={"file": (receipt_path.name, f, "application/pdf")},
        )
    receipt_resp.raise_for_status()
    data = receipt_resp.json()

    verdict = data.get("verdict") or {}
    predicted_verdict = verdict.get("verdict", "")
    expected_verdict = case["expected_verdict"]
    cited_doc_ids = [c["doc_id"] for c in verdict.get("cited_clauses", [])]
    expected_doc_ids = case.get("expected_doc_ids", [])

    verdict_match = predicted_verdict == expected_verdict
    citation_relevance = (
        any(d in cited_doc_ids for d in expected_doc_ids)
        if expected_doc_ids
        else bool(cited_doc_ids)
    )
    has_citations = len(verdict.get("cited_clauses", [])) > 0
    confidence_not_low = verdict.get("confidence", "LOW") != "LOW"

    return {
        "case_id": case.get("id", "unknown"),
        "type": "verdict",
        "expected_verdict": expected_verdict,
        "predicted_verdict": predicted_verdict,
        "verdict_match": verdict_match,
        "citation_relevance": citation_relevance,
        "has_citations": has_citations,
        "confidence_not_low": confidence_not_low,
        "confidence": verdict.get("confidence"),
        "cited_doc_ids": cited_doc_ids,
    }


def run_qa_case(client: httpx.Client, base_url: str, case: dict) -> dict:
    resp = client.post(build_url(base_url, "/api/policy-qa"), json={"question": case["question"]})
    resp.raise_for_status()
    data = resp.json()

    refused = data.get("refused", False)
    expected_refuse = case.get("expected_refuse", False)
    citations = data.get("citations", [])
    cited_doc_ids = [c["doc_id"] for c in citations]
    expected_doc_ids = case.get("expected_doc_ids", [])

    refusal_match = refused == expected_refuse
    citation_relevance = (
        any(d in cited_doc_ids for d in expected_doc_ids)
        if (expected_doc_ids and not refused)
        else True
    )

    return {
        "case_id": case.get("id", "unknown"),
        "type": "qa",
        "question": case["question"],
        "expected_refuse": expected_refuse,
        "refused": refused,
        "refusal_match": refusal_match,
        "citation_relevance": citation_relevance,
        "cited_doc_ids": cited_doc_ids,
    }


def print_results_table(metrics: dict, results: list[dict]) -> None:
    print("\n" + "=" * 65)
    print("  NORTHWIND EXPENSE AI — EVAL RESULTS")
    print("=" * 65)

    print(f"\n  {'ID':<28} {'TYPE':<9} {'PASS':<6} DETAIL")
    print(f"  {'-'*28} {'-'*9} {'-'*6} {'-'*32}")
    for r in results:
        if r.get("error"):
            status = "ERROR"
            detail = r["error"][:40]
        elif r["type"] == "verdict":
            status = "PASS" if r["verdict_match"] else "FAIL"
            detail = (
                f"expected={r['expected_verdict']} "
                f"got={r['predicted_verdict']} "
                f"conf={r.get('confidence', '?')}"
            )
        else:
            status = "PASS" if r["refusal_match"] else "FAIL"
            detail = f"refused={r['refused']} (expected={r['expected_refuse']})"
        print(f"  {r['case_id']:<28} {r['type']:<9} {status:<6} {detail}")

    print(f"\n  {'Metric':<26} {'Score':>7}  {'Weight':>7}")
    print(f"  {'-'*26} {'-'*7}  {'-'*7}")
    weighted = [
        ("verdict_accuracy",   "Verdict Accuracy",   "40%"),
        ("citation_relevance", "Citation Relevance", "25%"),
        ("refusal_accuracy",   "Refusal Accuracy",   "20%"),
        ("confidence_rate",    "Confidence Rate",    "15%"),
    ]
    for key, label, weight in weighted:
        val = metrics.get(key, 0.0)
        print(f"  {label:<26} {val:>6.1%}   {weight:>6}")
    print(f"  {'─'*26} {'─'*7}  {'─'*7}")
    print(f"  {'OVERALL SCORE':<26} {metrics['overall_score']:>6.1%}")
    print("=" * 65 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Northwind Expense AI eval harness")
    parser.add_argument("--input", required=True, help="Path to eval cases JSON file")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    cases = json.loads(Path(args.input).read_text())
    base_url = args.base_url.rstrip("/")

    results: list[dict] = []

    with httpx.Client(timeout=TIMEOUT) as client:
        for case in cases:
            case_id = case.get("id", "?")
            case_type = case.get("type", "?")
            print(f"Running [{case_type}] {case_id} ...", flush=True)
            try:
                if case_type == "verdict":
                    result = run_verdict_case(client, base_url, case)
                elif case_type == "qa":
                    result = run_qa_case(client, base_url, case)
                else:
                    print(f"  Unknown type '{case_type}', skipping.")
                    continue

                results.append(result)
                if case_type == "verdict":
                    ok = result["verdict_match"]
                else:
                    ok = result["refusal_match"]
                outcome = result.get("predicted_verdict") or ("refused" if result.get("refused") else "answered")
                print(f"  {'PASS' if ok else 'FAIL'} -> {outcome}")

            except Exception as exc:
                print(f"  ERROR: {exc}")
                results.append({
                    "case_id": case_id,
                    "type": case_type,
                    "error": str(exc),
                    "verdict_match": False,
                    "refusal_match": False,
                    "citation_relevance": False,
                    "confidence_not_low": False,
                })

    metrics = {
        "verdict_accuracy":   compute_verdict_accuracy(results),
        "citation_relevance": compute_citation_relevance(results),
        "refusal_accuracy":   compute_refusal_accuracy(results),
        "confidence_rate":    compute_confidence_rate(results),
    }
    metrics["overall_score"] = compute_overall_score(metrics)

    print_results_table(metrics, results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(__file__).parent / f"results_{timestamp}.json"
    out_path.write_text(json.dumps({
        "timestamp": timestamp,
        "base_url": base_url,
        "metrics": metrics,
        "results": results,
    }, indent=2))
    print(f"Results saved to {out_path}\n")


if __name__ == "__main__":
    main()
