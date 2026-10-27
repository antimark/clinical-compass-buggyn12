"""Small deterministic lexical fixture baseline. NOT trained/clinically validated NLP."""
from __future__ import annotations
import re

# Intentionally small patterns: unrecognized language is omitted, not guessed.
PATTERNS: tuple[tuple[str, str], ...] = (
    ("sleep_disturbance", r"(?:последние\s+\w+\s+дня\s+)?плохо\s+спл(?:ю|ал|ала)|бессонниц\w*|не\s+мог(?:у|ла|)\s+уснуть"),
    ("work", r"из-за\s+работы|\bработ(?:а|е|у|ы|ой)\b|карьер\w*"),
    ("family", r"\bсемь(?:я|е|ю|и|ёй)\b|родител\w*"),
    ("relationships", r"отношени\w*|расставани\w*"),
    ("anxiety", r"пережива(?:ю|л|ла|ет)|тревож\w*"),
    ("fatigue", r"\bустал(?:а|ость|)\b|утомл\w*"),
    ("concentration_difficulty", r"не\s+мог(?:у|ла)?\s+сосредоточиться|трудно\s+концентрироваться"),
    ("low_mood", r"подавленн\w*|сниженно(?:е|го)\s+настроени\w*"),
    ("suicidal_ideation_reported", r"суицидальн\w*\s+мысл\w*"),
    ("self_harm_reported", r"самоповреждени\w*"),
    ("interpersonal_conflict", r"конфликт\w*|поссорил(?:ся|ась)"),
    ("positive_event", r"порадовал\w*|хорош(?:ий|ая)\s+новост\w*"),
)

NEG_RE = re.compile(r"\b(?:отрица(?:ю|ет|ют)|не\s+было|не\s+(?:тревож\w*|пережива\w*)|никогда\s+не|нет)\b", re.I)
PAST_RE = re.compile(r"\b(?:раньше|в\s+прошлом|прежде|вчера|на\s+прошлой\s+неделе)\b", re.I)
OTHER_RE = re.compile(r"\b(?:знакомый|друг|подруга|мама|коллега|врач)\s+(?:сказал|сказала|рассказал|говорит|сообщил)\b", re.I)


class DeterministicMockProvider:
    name = "deterministic_mock"
    model_id = "lexical-fixture-baseline-v0.1"

    def extract(self, source, catalog, prompt_version):
        allowed = {t["code"] for t in catalog["tags"] if t["enabled_for_llm"]}
        text = source.body_text
        facts = []
        for code, pattern in PATTERNS:
            if code not in allowed:
                continue
            for match in re.finditer(pattern, text, flags=re.I):
                s, e = match.span()
                # Sentence context for simple, conservative negative/past handling.
                left = max(text.rfind(".", 0, s), text.rfind("!", 0, s), text.rfind("?", 0, s), text.rfind("\n", 0, s)) + 1
                candidates = [x for x in (text.find(".", e), text.find("!", e), text.find("?", e), text.find("\n", e)) if x >= 0]
                right = min(candidates) if candidates else len(text)
                ctxt = text[left:right]
                assertion = "negated" if NEG_RE.search(ctxt) else "asserted"
                temporality = "past" if PAST_RE.search(ctxt) else "current"
                speaker = source.author_role
                if OTHER_RE.search(ctxt):
                    speaker = "unknown"
                    assertion = "uncertain"
                facts.append({
                    "tag_code": code, "assertion": assertion, "temporality": temporality,
                    "evidence": {"start": s, "end": e, "quote": text[s:e]},
                    "speaker": speaker, "review_status": "proposed"
                })
        # Canonical order makes fixture output stable.
        facts.sort(key=lambda f: (f["evidence"]["start"], f["tag_code"]))
        return {"facts": facts[:64], "missing_information": []}
