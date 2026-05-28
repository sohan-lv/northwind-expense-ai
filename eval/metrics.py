"""
Metrics functions for the Northwind Expense AI eval harness.
Each function takes the full results list and returns a float in [0, 1].
"""


def compute_verdict_accuracy(results: list[dict]) -> float:
    """Fraction of verdict cases where predicted verdict matches expected."""
    verdict_cases = [r for r in results if r["type"] == "verdict"]
    if not verdict_cases:
        return 0.0
    correct = sum(1 for r in verdict_cases if r.get("verdict_match", False))
    return correct / len(verdict_cases)


def compute_citation_relevance(results: list[dict]) -> float:
    """Fraction of verdict cases where at least one expected doc_id appears in cited_clauses."""
    verdict_cases = [r for r in results if r["type"] == "verdict"]
    if not verdict_cases:
        return 0.0
    relevant = sum(1 for r in verdict_cases if r.get("citation_relevance", False))
    return relevant / len(verdict_cases)


def compute_refusal_accuracy(results: list[dict]) -> float:
    """Fraction of Q&A cases where the refusal behaviour matches expected."""
    qa_cases = [r for r in results if r["type"] == "qa"]
    if not qa_cases:
        return 0.0
    correct = sum(1 for r in qa_cases if r.get("refusal_match", False))
    return correct / len(qa_cases)


def compute_confidence_rate(results: list[dict]) -> float:
    """Fraction of verdict cases where confidence is not LOW."""
    verdict_cases = [r for r in results if r["type"] == "verdict"]
    if not verdict_cases:
        return 0.0
    not_low = sum(1 for r in verdict_cases if r.get("confidence_not_low", False))
    return not_low / len(verdict_cases)


def compute_overall_score(metrics: dict) -> float:
    """Weighted average of the four core metrics."""
    weights = {
        "verdict_accuracy":   0.40,
        "citation_relevance": 0.25,
        "refusal_accuracy":   0.20,
        "confidence_rate":    0.15,
    }
    total = sum(metrics.get(k, 0.0) * w for k, w in weights.items())
    return total
