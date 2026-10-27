from __future__ import annotations
import json
import re
from pathlib import Path
from jsonschema import Draft202012Validator
from .catalog import tag_map
from .errors import ValidationRejected
from .models import SourceRecord

NEGATION = re.compile(r"\b(?:отрица(?:ю|ет|ют|л|ла)|не\s+(?:было|испытыва(?:ю|ет)|хочу|думаю|тревож\w*|пережива\w*)|нет|отсутству(?:ет|ют)|никогда\s+не)\b", re.I)
PAST = re.compile(r"\b(?:раньше|прежде|в\s+прошлом|тогда|в\s+детстве|до\s+этого|вчера|на\s+прошлой\s+неделе)\b", re.I)
SPEAKER_OTHER = re.compile(r"\b(?:знакомый|друг|подруга|мама|отец|коллега|врач|другой\s+человек)\s+(?:сказал|рассказал|говорит|сказала|сообщил|сообщила)\b|\bсо\s+слов\b", re.I)


def load_schema(path: str | Path) -> dict:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validate_output(result: dict, source: SourceRecord, catalog: dict, schema: dict) -> None:
    validator = Draft202012Validator(schema)
    if not validator.is_valid(result):
        raise ValidationRejected("invalid_extraction_schema")
    if (result["source_id"] != source.source_id or result["source_revision"] != source.source_revision
            or result["source_type"] != source.source_type or result["tag_catalog_version"] != catalog["catalog_version"]):
        raise ValidationRejected("source_metadata_mismatch")
    tags = tag_map(catalog)
    seen = set()
    for fact in result["facts"]:
        code = fact["tag_code"]
        if code not in tags or not tags[code]["enabled_for_llm"]:
            raise ValidationRejected("unknown_or_disabled_tag")
        ev = fact["evidence"]
        start, end, quote = ev["start"], ev["end"], ev["quote"]
        if end <= start or end > len(source.body_text) or source.body_text[start:end] != quote:
            raise ValidationRejected("evidence_offset_mismatch")
        # The exact same span/tag may not be repeated to inflate frequency.
        key = (code, start, end)
        if key in seen:
            raise ValidationRejected("duplicate_fact")
        seen.add(key)


def conservative_context_guard(result: dict, source: SourceRecord) -> dict:
    """Conservative checks, not a perfect natural-language understanding engine.

    A suspicious positive/current fact is downgraded to uncertain/unknown instead of
    being promoted to a positive clinical assertion. Cross-sentence context is bounded.
    """
    new_facts = []
    text = source.body_text
    for original in result["facts"]:
        fact = dict(original)
        s, e = fact["evidence"]["start"], fact["evidence"]["end"]
        # Local sentence only, so negation in a separate sentence won't override this fact.
        before = max(text.rfind(".", 0, s), text.rfind("!", 0, s), text.rfind("?", 0, s), text.rfind("\n", 0, s))
        after_candidates = [p for p in (text.find(".", e), text.find("!", e), text.find("?", e), text.find("\n", e)) if p != -1]
        after = min(after_candidates) if after_candidates else len(text)
        context = text[max(before+1, s-70):min(after, e+70)]
        # Especially important: a quote from a third party is not proof of patient's symptom.
        if SPEAKER_OTHER.search(context):
            fact["speaker"] = "unknown"
            if fact["assertion"] == "asserted":
                fact["assertion"] = "uncertain"
        if NEGATION.search(context) and fact["assertion"] == "asserted":
            fact["assertion"] = "uncertain"
        if PAST.search(context) and fact["temporality"] == "current":
            fact["temporality"] = "unknown"
        new_facts.append(fact)
    return {**result, "facts": new_facts}
