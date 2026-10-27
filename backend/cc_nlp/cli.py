"""Local synthetic-only CLI. No HTTP server, no DB, no patient ID, no file logging."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from importlib.resources import files
from .catalog import load_catalog
from .models import SourceRecord, ProcessingAuthorization
from .validator import load_schema
from .pipeline import analyze
from .providers.mock import DeterministicMockProvider
from .providers.ollama import LocalOllamaProvider
from .evaluation import evaluate_case_results

ROOT = Path(__file__).resolve().parents[2]


def resources(root: Path):
    base = root if (root / "catalog/tags.v0.1.json").exists() else files("cc_nlp").joinpath("assets")
    catalog_path = base / "catalog/tags.v0.1.json" if base == root else base / "tags.v0.1.json"
    catalog_schema = base / "contracts/schemas/tag_catalog.schema.json" if base == root else base / "tag_catalog.schema.json"
    extraction_schema = base / "contracts/schemas/extraction_result.schema.json" if base == root else base / "extraction_result.schema.json"
    catalog = load_catalog(catalog_path, schema_path=catalog_schema)
    schema = load_schema(extraction_schema)
    return catalog, schema


def source_from_dict(data):
    if data.get("synthetic") is not True:
        raise ValueError("cli_accepts_only_explicit_synthetic_fixtures")
    return SourceRecord(source_id=data["source_id"], source_revision=data.get("source_revision", 1),
                        source_type=data.get("source_type", "journal_entry"), body_text=data["body_text"],
                        visibility=data.get("visibility", "shared_with_care_team"),
                        author_role=data.get("author_role", "patient"))


def provider_from_args(args):
    if args.provider == "mock":
        return DeterministicMockProvider()
    if not args.model:
        raise ValueError("local_model_name_required")
    return LocalOllamaProvider(model=args.model)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cc-nlp", description="Standalone Phase6 synthetic NLP lab")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyze", help="Analyze one explicitly synthetic JSON fixture")
    p.add_argument("--source", required=True)
    p.add_argument("--provider", choices=["mock", "ollama"], default="mock")
    p.add_argument("--model", help="Locally installed Ollama model, e.g. your-verified-model-tag")
    p.add_argument("--audience", choices=["patient", "doctor"], default="doctor")
    p.add_argument("--private-opt-in", action="store_true")
    p = sub.add_parser("evaluate", help="Run miniature synthetic baseline evaluation")
    p.add_argument("--corpus", default=None)
    p.add_argument("--provider", choices=["mock", "ollama"], default="mock")
    p.add_argument("--model")
    args = parser.parse_args(argv)
    cat, schema = resources(ROOT)
    provider = provider_from_args(args)
    if args.command == "analyze":
        source = source_from_dict(json.loads(Path(args.source).read_text(encoding="utf-8")))
        auth = ProcessingAuthorization(audience=args.audience, source_access_granted=True,
                                       private_analysis_opt_in=args.private_opt_in)
        outcome = analyze(source, auth, provider, catalog=cat, schema=schema)
        print(json.dumps({"result": outcome.result, "error_code": outcome.error_code,
                          "model_id": outcome.model_id, "prompt_version": outcome.prompt_version}, ensure_ascii=False, indent=2))
        return 0 if outcome.error_code is None else 2
    corpus_file = Path(args.corpus) if args.corpus else (ROOT / "fixtures/synthetic_eval.json" if (ROOT / "fixtures/synthetic_eval.json").exists() else files("cc_nlp").joinpath("assets/synthetic_eval.json"))
    corpus = json.loads(corpus_file.read_text(encoding="utf-8"))
    items = []
    for case in corpus:
        source = source_from_dict(case["source"])
        auth = ProcessingAuthorization(audience="doctor", source_access_granted=True)
        result = analyze(source, auth, provider, catalog=cat, schema=schema)
        items.append({"gold_positive_tags": case["gold_positive_tags"],
                      "forbidden_positive_tags": case.get("forbidden_positive_tags", []),
                      "result": result.result})
    print(json.dumps(evaluate_case_results(items), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
