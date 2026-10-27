"""Loopback-only local Ollama adapter; uses stdlib HTTP and JSON Schema response format."""
from __future__ import annotations
import json
import copy
import re
import threading
from importlib.resources import files
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from jsonschema import Draft202012Validator
from ..errors import ValidationRejected
from ..errors import ProviderUnavailable

INFERENCE_GATE = threading.BoundedSemaphore(1)


class _DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_versioned_system_prompt() -> str:
    return files("cc_nlp").joinpath("prompt_templates/extract_v1.txt").read_text(encoding="utf-8")



class LocalOllamaProvider:
    name = "local_llm"

    def __init__(self, *, model: str, base_url: str = "http://127.0.0.1:11434", timeout_seconds: int = 90):
        url = urlsplit(base_url)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
            raise ValueError("only_loopback_ollama_endpoint_allowed")
        if not model.strip() or any(x in model for x in "\n\r\x00"):
            raise ValueError("invalid_model_id")
        self.model_id = model
        self.url = base_url.rstrip("/") + "/api/chat"
        self.timeout_seconds = timeout_seconds

    def extract(self, source, catalog, prompt_version):
        # Shared by scoped CI and synthetic lab in this single-process prototype.
        if not INFERENCE_GATE.acquire(blocking=False):
            raise ProviderUnavailable("local_inference_busy")
        try:
            return self._extract(source, catalog, prompt_version)
        finally:
            INFERENCE_GATE.release()

    def _extract(self, source, catalog, prompt_version):
        # Keep a narrow LLM response contract. Trusted source metadata never comes from LLM.
        fact = {
            "type": "object", "additionalProperties": False,
            "required": ["tag_code", "assertion", "temporality", "evidence", "speaker", "review_status"],
            "properties": {
                "tag_code": {"type": "string", "enum": [t["code"] for t in catalog["tags"] if t["enabled_for_llm"]]},
                "assertion": {"type": "string", "enum": ["asserted", "negated", "uncertain"]},
                "temporality": {"type": "string", "enum": ["current", "past", "future", "unknown"]},
                "evidence": {"type": "object", "additionalProperties": False, "required": ["quote"],
                             "properties": {"quote": {"type": "string", "minLength": 1, "maxLength": 2000}}},
                "speaker": {"type": "string", "enum": ["patient", "clinician", "other", "unknown"]},
                "review_status": {"type": "string", "const": "proposed"},
            },
        }
        output_schema = {
            "type": "object", "additionalProperties": False, "required": ["facts", "missing_information"],
            "properties": {"facts": {"type": "array", "maxItems": 64, "items": fact},
                           "missing_information": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 80}}},
        }
        user_text = json.dumps({
            "source_type": source.source_type, "author_role": source.author_role,
            "allowed_tag_codes": [t["code"] for t in catalog["tags"] if t["enabled_for_llm"]],
            "text": source.body_text,
        }, ensure_ascii=False)
        # Constrain generation to verbatim source excerpts. The model still
        # chooses tags/assertion/time/speaker; trusted code supplies no labels.
        # Retain the independent exact-span validator below, including rejection
        # of changed or ambiguous quotes even if a provider ignores the schema.
        candidates = []
        for match in re.finditer(r'[^.!?\n]+[.!?]*', source.body_text):
            sentence = match.group().strip()
            for offset in range(0, len(sentence), 2000):
                quote = sentence[offset:offset + 2000]
                if quote and source.body_text.count(quote) == 1 and quote not in candidates:
                    candidates.append(quote)
        if 0 < len(source.body_text) <= 2000 and source.body_text not in candidates:
            candidates.append(source.body_text)
        wire_schema = copy.deepcopy(output_schema)
        if candidates:
            wire_schema['properties']['facts']['items']['properties']['evidence']['properties']['quote']['enum'] = candidates[:64]
        payload = {"model": self.model_id, "stream": False, "think": False, "format": wire_schema,
                   "messages": [{"role": "system", "content": load_versioned_system_prompt() + "\nДля локального wire-контракта evidence содержит только quote. Выбирай дословную цитату, которая встречается ровно один раз в исходном text. Индексы вычисляет сервер; start/end не выводи."},
                                {"role": "user", "content": user_text}],
                   "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 1024}}
        # Reject proxies to avoid sending clinical text outside loopback.
        opener = build_opener(ProxyHandler({}), _DenyRedirect())
        request = Request(self.url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                blob = response.read(1_000_001)
                if len(blob) > 1_000_000:
                    raise ProviderUnavailable("response_too_large")
        except HTTPError as exc:
            raise ProviderUnavailable("model_unavailable" if exc.code == 404 else "local_http_failure") from None
        except TimeoutError:
            raise ProviderUnavailable("local_timeout") from None
        except URLError as exc:
            raise ProviderUnavailable("local_timeout" if isinstance(exc.reason, TimeoutError) else "local_transport_failure") from None
        except OSError:
            raise ProviderUnavailable("local_transport_failure") from None
        try:
            message = json.loads(blob)["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise ProviderUnavailable("invalid_ollama_response") from None
        try:
            parsed = json.loads(message)
        except (ValueError, TypeError):
            raise ProviderUnavailable("invalid_model_json") from None
        if not Draft202012Validator(output_schema).is_valid(parsed):
            raise ValidationRejected("invalid_provider_payload")
        # Mechanical indexing belongs to trusted code, not the language model.
        # Exact unique substrings only: no Unicode/whitespace/case repair.
        for item in parsed["facts"]:
            quote = item["evidence"]["quote"]
            start = source.body_text.find(quote)
            if start < 0:
                raise ValidationRejected("evidence_quote_absent")
            if source.body_text.find(quote, start + 1) >= 0:
                raise ValidationRejected("evidence_quote_ambiguous")
            item["evidence"] = {"quote": quote, "start": start, "end": start + len(quote)}
        # The pipeline still validates the full schema and every exact evidence span.
        return parsed
