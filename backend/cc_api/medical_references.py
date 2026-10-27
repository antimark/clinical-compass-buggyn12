"""Lossless, fingerprinted source imports and exact auditable demo mappings."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from .reference_models import DrugReference, ReferenceMatchRule, TherapyReference

DATA_DIR = Path(__file__).parent / 'data' / 'medications'
FILENAME_ALIASES = {'aviandr_maritupirdine_instruction(2).json': 'aviandr_maritupirdine_instruction.json'}
MATCH_LIMITATION = 'Не является медицинской рекомендацией; проверьте показания, противопоказания и данные пациента'
REFERENCE_LIMITATION = 'Импортированный справочный текст не прошёл независимую медицинскую проверку в проекте. Не является персональным назначением.'
THERAPY_LIMITATION = 'Иллюстративная справочная карточка для проверки интерфейса. Не утверждённый клинический протокол и не назначение пациенту.'

TITLES = {
    'schema_version': 'Версия схемы источника', 'record_type': 'Тип записи', 'language': 'Язык',
    'product': 'Препарат', 'indications_and_dosing': 'Показания и дозирование — справочная информация',
    'administration_instructions': 'Способ применения', 'adverse_event_frequency_definitions': 'Частота нежелательных явлений',
    'adverse_effects': 'Нежелательные реакции', 'contraindications': 'Противопоказания',
    'excipient_warnings': 'Предупреждения о вспомогательных веществах', 'precautions': 'Меры предосторожности',
    'drug_interactions': 'Лекарственные взаимодействия', 'special_populations': 'Особые группы',
    'storage': 'Хранение', 'clinical_decision_support': 'Справочные сведения источника',
    'sources': 'Источники', 'verification': 'Сведения о проверке в исходном файле',
    'regulatory_records': 'Регистрационные сведения', 'evidence': 'Сведения об исследованиях',
    'trial_links': 'Ссылки на исследования',
}


def load_bundled_references():
    """Fail closed on count, alias, traversal, schema or any source hash mismatch."""
    manifest = json.loads((DATA_DIR / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('record_count') != 8 or len(manifest.get('records', [])) != 8:
        raise ValueError('Medication manifest must contain exactly eight records')
    rows = []
    known = set()
    for entry in manifest['records']:
        declared = entry['filename']
        filename = FILENAME_ALIASES.get(declared, declared)
        if Path(filename).name != filename or not filename.endswith('.json') or filename in known:
            raise ValueError('Invalid or duplicate source filename')
        known.add(filename)
        raw = (DATA_DIR / filename).read_bytes()
        fingerprint = hashlib.sha256(raw).hexdigest()
        if fingerprint != entry['sha256']:
            raise ValueError('Medication source hash mismatch: ' + filename)
        content = json.loads(raw.decode('utf-8'))
        if not isinstance(content, dict) or not isinstance(content.get('product'), dict) or not content.get('schema_version'):
            raise ValueError('Unsupported source structure')
        rows.append(dict(id=Path(filename).stem, version='sha256_' + fingerprint,
            source_filename=filename, manifest_filename=declared, fingerprint=fingerprint,
            raw=raw, content=content))
    return rows


def resolve_medication_reference(reference_id, reference_version):
    for entry in load_bundled_references():
        if entry['id'] == reference_id and entry['version'] == reference_version:
            product = entry['content']['product']
            return dict(id=entry['id'], version=entry['version'], title=product['name'],
                inn=product.get('international_nonproprietary_name', ''), import_fingerprint=entry['fingerprint'])
    return None


def typed_sections(content):
    """Preserve all source values; presentation may omit null/empty optional nodes."""
    sections = []
    for key, value in content.items():
        if value is None or value == '' or value == [] or value == {}:
            kind = 'null_omit'
        elif key in ('contraindications', 'precautions', 'excipient_warnings'):
            kind = 'warning'
        elif isinstance(value, list):
            kind = 'list'
        elif isinstance(value, dict):
            kind = 'nested'
        elif isinstance(value, bool):
            kind = 'boolean'
        elif isinstance(value, (int, float)):
            kind = 'number'
        else:
            kind = 'text'
        sections.append(dict(key=key, title=TITLES.get(key, key.replace('_', ' ').capitalize()), type=kind, value=value))
    return sections


def compact_reference(row):
    source = json.loads(row.structured_json)
    return dict(id=row.id, version=row.version, title=row.title, inn=row.inn, review_status=row.review_status,
        product=source.get('product', {}), source_filename=row.source_filename,
        import_fingerprint=row.import_fingerprint)


def detailed_reference(row):
    return dict(compact_reference(row), sections=typed_sections(json.loads(row.structured_json)),
        provenance=dict(source_filename=row.source_filename, manifest_filename=row.manifest_filename,
            sha256=row.import_fingerprint, schema_version=row.schema_version, review_status=row.review_status),
        limitation=REFERENCE_LIMITATION)


CBT_CONTENT = dict(method_id='cbt_demo_v1', name='Когнитивно-поведенческая терапия (КПТ)',
    short_description='Иллюстративный пример структуры справочника методов терапии.',
    sections=[dict(key='overview', title='Обзор карточки', type='text',
        value='Демонстрационный раздел для описания метода после отдельного медицинского редактирования.'),
        dict(key='discussion', title='Обсуждение со специалистом', type='list',
            value=['Цели обсуждаются с лечащим специалистом.', 'Индивидуальный план оформляется отдельной врачебной записью.']),
        dict(key='limits', title='Ограничения примера', type='warning', value=THERAPY_LIMITATION)],
    expandable_fields=['overview', 'discussion', 'limits'], limitations_text=THERAPY_LIMITATION,
    review_status='illustrative_unreviewed', version='1')


def seed_medical_references(SessionLocal):
    imports = load_bundled_references()
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    with SessionLocal.begin() as db:
        for entry in imports:
            content = entry['content']
            product = content['product']
            row = db.get(DrugReference, (entry['id'], entry['version']))
            if row:
                if (row.import_fingerprint != entry['fingerprint'] or row.raw_original_json.encode('utf-8') != entry['raw']
                        or json.loads(row.structured_json) != content):
                    raise ValueError('Existing immutable reference differs from verified source')
            else:
                db.add(DrugReference(id=entry['id'], version=entry['version'],
                    reference_type=content.get('record_type', 'medicinal_product_instruction'),
                    schema_version=content['schema_version'], review_status='imported_unreviewed',
                    title=product['name'], inn=product.get('international_nonproprietary_name', ''),
                    raw_original_json=entry['raw'].decode('utf-8'), import_fingerprint=entry['fingerprint'],
                    source_filename=entry['source_filename'], manifest_filename=entry['manifest_filename'],
                    imported_at=now, structured_json=json.dumps(content, ensure_ascii=False)))
            db.flush()
            # No text mining, parent-code expansion, dosage copying or indication inference.
            for index, indication in enumerate(content.get('indications_and_dosing', [])):
                for code_index, code in enumerate(indication.get('icd10_codes', [])):
                    pointers = [f'/indications_and_dosing/{index}/icd10_codes/{code_index}',
                                f'/indications_and_dosing/{index}/diagnosis_or_condition']
                    digest = hashlib.sha256((entry['id'] + ':' + entry['version'] + ':' + str(index) + ':' + str(code_index)).encode()).hexdigest()[:48]
                    rid = 'rm_' + digest
                    if not db.get(ReferenceMatchRule, rid):
                        db.add(ReferenceMatchRule(id=rid, version='1', icd10_code=code,
                            drug_reference_id=entry['id'], drug_reference_version=entry['version'],
                            match_basis=indication['diagnosis_or_condition'], source_field_paths_json=json.dumps(pointers),
                            curation_status='synthetic_demo', environment_scope='synthetic_dev',
                            created_by='source_import', reviewed_by=None, display_limitation=MATCH_LIMITATION))
        if not db.get(TherapyReference, ('cbt_demo_v1', '1')):
            db.add(TherapyReference(id='cbt_demo_v1', version='1', title=CBT_CONTENT['name'],
                review_status='illustrative_unreviewed', content_json=json.dumps(CBT_CONTENT, ensure_ascii=False)))
