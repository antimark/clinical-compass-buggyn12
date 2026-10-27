"""Versioned technical examples. No validated clinical scale or interpretation."""
import json
from functools import lru_cache
from pathlib import Path

DISCLAIMER = 'Демонстрационный опросник. Не является медицинской оценкой.'
TECHNICAL_NOTE = 'Невалидированный технический пример для проверки интерфейса и сохранения ответов.'
METRICS = {
    ('wellbeing', 'points', 'mood_1_5_v1'): ('Самочувствие · 1–5', 1, 5),
    ('wellbeing', 'points', 'mood_0_10_v1'): ('Самочувствие · 0–10', 0, 10),
    ('sleep', 'hours', 'sleep_hours_v1'): ('Продолжительность сна · часы', 0, 24),
}


def definition_payload(count):
    return {'id': f'demo_{count}_v1', 'version': '1', 'title': f'Демонстрационный опросник · {count} вопросов',
        'language': 'ru', 'status': 'synthetic_demo', 'pages': [10] if count == 10 else [10, 5],
        'questions': [{'id': f'q{i}', 'label': f'Технический вопрос {i}: выберите значение от 1 до 4.'} for i in range(1, count + 1)],
        'options': [1, 2, 3, 4], 'disclaimer': DISCLAIMER, 'technical_note': TECHNICAL_NOTE}


DEFINITIONS = [definition_payload(10), definition_payload(15)]

# These are NOT approved clinical releases. They are source-pinned, draft Russian
# evaluation forms; the public clinical catalog continues to exclude item text.
EVALUATION_INSTRUMENTS = ('phq_9', 'phq_2', 'gad_7', 'gad_2')

@lru_cache(maxsize=1)
def evaluation_definitions():
    root = Path(__file__).resolve().parents[2] / 'clinical_catalog_data' / 'v5' / 'catalog' / 'instruments'
    definitions = []
    for identifier in EVALUATION_INSTRUMENTS:
        raw = json.loads((root / (identifier + '.json')).read_text(encoding='utf-8'))
        questions = []
        for source in raw['questions']:
            if source.get('type') != 'single_choice' or not source.get('required'):
                raise ValueError('Unsupported evaluation questionnaire item: ' + identifier)
            options = [{'value': int(o['score']), 'label': str(o['label'])} for o in source['options']]
            if len(set(o['value'] for o in options)) != len(options):
                raise ValueError('Duplicate questionnaire score: ' + identifier)
            questions.append({'id': source['id'], 'label': source['text'], 'options': options})
        scoring = raw['scoring']
        if scoring.get('type') != 'sum' or scoring.get('item_ids') != [q['id'] for q in questions]:
            raise ValueError('Unsupported scoring specification: ' + identifier)
        minimum, maximum = sum(min(o['value'] for o in q['options']) for q in questions), sum(max(o['value'] for o in q['options']) for q in questions)
        if (minimum, maximum) != (scoring['min_score'], scoring['max_score']):
            raise ValueError('Catalog range mismatch: ' + identifier)
        definitions.append({
            'id': 'eval_' + identifier + '_v1', 'version': raw['instrument_version'],
            'source_id': identifier, 'source_version': raw['instrument_version'],
            'title': raw['information']['title']['ru'] + ' (' + raw['information']['title']['short'] + ')',
            'language': raw['language'], 'status': 'evaluation_draft_unapproved',
            'pages': [len(questions)], 'questions': questions, 'min_score': minimum,
            'max_score': maximum, 'scoring_method': 'sum',
            'disclaimer': 'Только для тестирования на вымышленных данных. Русская редакция ожидает медицинского и правового утверждения. Балл не является диагнозом.',
            'technical_note': 'Результат — сумма ответов (0–3). Интерпретация и клинические выводы отключены до утверждения редакции.'
        })
    return definitions



def _valid_options(definition, question):
    if definition.get('status') == 'evaluation_draft_unapproved':
        return {option['value'] for option in question['options']}
    return {1, 2, 3, 4}


def validate_answers(definition, answers, *, require_complete=False):
    if not isinstance(answers, dict):
        raise ValueError('Answers must be an object')
    questions = {q['id']: q for q in definition['questions']}
    if not set(answers).issubset(questions) or (require_complete and set(answers) != set(questions)):
        raise ValueError('Missing or unknown questionnaire questions')
    if any(type(value) is not int or value not in _valid_options(definition, questions[qid]) for qid, value in answers.items()):
        raise ValueError('Invalid questionnaire option')
    return True


def score_answers(definition, answers):
    validate_answers(definition, answers, require_complete=True)
    return sum(answers.values())


def submission_payload(row):
    definition = json.loads(row.definition_snapshot_json)
    answers = json.loads(row.answers_json)
    clinical_draft = definition.get('status') == 'evaluation_draft_unapproved'
    return {'id': row.id, 'assignment_id': row.assignment_id, 'definition_id': row.definition_id,
        'definition_version': row.definition_version, 'title': definition['title'],
        'status': 'submitted', 'score': row.score, 'min_score': definition.get('min_score', len(definition['questions'])),
        'max_score': definition.get('max_score', len(definition['questions']) * 4),
        'submitted_at': row.submitted_at, 'disclaimer': definition['disclaimer'],
        'technical_note': definition.get('technical_note', TECHNICAL_NOTE), 'evaluation_draft': clinical_draft,
        'answers': [{'question_id': q['id'], 'label': q['label'], 'value': answers[q['id']],
                     'answer_label': next((o['label'] for o in q['options'] if o['value'] == answers[q['id']]), str(answers[q['id']])) if clinical_draft else str(answers[q['id']])}
                    for q in definition['questions']]}
