from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from .errors import ValidationRejected


def load_catalog(path: str | Path, *, schema_path: str | Path | None = None) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if schema_path:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        if not Draft202012Validator(schema).is_valid(data):
            raise ValidationRejected("invalid_catalog_schema")
    codes = [t["code"] for t in data["tags"]]
    if len(codes) != len(set(codes)):
        raise ValidationRejected("duplicate_tag_codes")
    return data


def tag_map(catalog: dict) -> dict:
    return {tag["code"]: tag for tag in catalog["tags"]}
