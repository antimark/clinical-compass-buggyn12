"""Verified, version-pinned Russian ICD titles; explicitly limited demo coverage."""
import json
from pathlib import Path
ARCHIVE = json.loads((Path(__file__).parent/'data/icd10_ru_subset_v1.json').read_text())
DATA = json.loads((Path(__file__).parent/'data/icd10_ru_subset_v2.json').read_text())
ICD_VERSION = DATA['version']

def search_icd10(query):
    query = query.strip().casefold()
    return [dict(item) for item in DATA['items'] if query in item['code'].casefold() or query in item['label'].casefold()]

def resolve_icd10(code, version):
    return next((dict(item) for item in DATA['items'] + ARCHIVE['items'] if code == item['code'] and version == item['version']), None)
