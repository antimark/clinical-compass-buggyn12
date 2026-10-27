"""Synthetic-only quality indicators. These metrics are NOT clinical validation."""
from __future__ import annotations
from collections import Counter


def positive_tags(result: dict) -> set[str]:
    return {f["tag_code"] for f in result["facts"] if f["assertion"] == "asserted"
            and f["temporality"] == "current" and f["speaker"] == "patient"}


SAFETY_TAGS = {"suicidal_ideation_reported", "suicidal_intent_reported", "suicidal_plan_reported",
               "self_harm_reported", "psychotic_symptoms_possible", "acute_neurological_symptoms"}


def evaluate_case_results(items: list[dict]) -> dict:
    """Input: [{gold_positive_tags:[...],result:{...}, forbidden_positive_tags:[...]}]."""
    tp = fp = fn = safety_fp = forbidden_fp = 0
    by_tag = Counter()
    for item in items:
        actual = positive_tags(item["result"])
        expected = set(item["gold_positive_tags"])
        tp += len(actual & expected)
        fp += len(actual - expected)
        fn += len(expected - actual)
        forbidden = actual & set(item.get("forbidden_positive_tags", []))
        forbidden_fp += len(forbidden)
        safety_fp += len(forbidden & SAFETY_TAGS)
        by_tag.update(actual & expected)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * precision * recall / (precision + recall) if (precision is not None and recall is not None and (precision + recall)) else None
    return {"evaluated_cases": len(items), "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1,
            "forbidden_positive_safety_matches": safety_fp,
            "forbidden_positive_matches": forbidden_fp,
            "note": "Toy gold set for technical checks only; not expert clinical validation."}
