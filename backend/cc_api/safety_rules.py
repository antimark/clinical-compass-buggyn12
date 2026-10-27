"""Bounded experimental lexical rules. Not clinical risk prediction or triage."""
import hashlib,json,re,unicodedata
from datetime import datetime,timezone
STATUS='experimental_needs_validation'
POLICY='evaluation-safety-lexical-v1'
NOTICE={'code':'seek_human_help','clinical_review_status':STATUS,'text':'Если опасность непосредственная, обратитесь за срочной очной человеческой помощью или в местную экстренную службу. Чат не является экстренной службой; врач не получает гарантированного уведомления и не наблюдает его круглосуточно.'}
RULES=[dict(rule_id='explicit-immediate-self-harm',version='1',pattern=r'(?<!\w)(?:я\s+)?(?:сейчас\s+хочу\s+навредить\s+себе|собираюсь\s+сейчас\s+навредить\s+себе)(?!\w)',signal_type='explicit_immediate_concern',severity='critical',critical=True,precedence=1),
 dict(rule_id='current-functional-concern',version='1',pattern=r'(?<!\w)(?:не\s+могу\s+спать\s+три\s+ночи|тревога\s+мешает\s+работать)(?!\w)',signal_type='functional_concern',severity='concern',critical=False,precedence=2)]
NEGATIVE=re.compile(r'\b(?:неправда|неверно|не\s+говорю|не\s+думаю|не\s+утверждаю|сообщил|сообщила|сообщает|говорит|по\s+словам|не\s+хочу|не\s+собираюсь|вчера|раньше|в\s+прошлом|если|когда-нибудь|цитата|сказал|сказала|друг|подруга|он|она|отрицаю|нет\s+мыслей)\b',re.I)

def evaluate(text):
    if not isinstance(text,str) or not text.strip() or len(text)>4000:return []
    if not '2026-10-26' <= datetime.now(timezone.utc).date().isoformat() < '2027-10-26':return []
    normalized=unicodedata.normalize('NFKC',text).lower()
    # Conservative entire utterance exclusion: ambiguity produces no critical label.
    if NEGATIVE.search(normalized) or any(c in normalized for c in '«»"“”'):return []
    found=[]
    for item in RULES:
        # Offsets must reference the original exact text, not normalization output.
        match=re.search(item['pattern'],text,re.I)
        if not match:continue
        rule={k:v for k,v in item.items() if k!='pattern'}
        rule.update(author='Clinical Compass evaluation engineering',reviewer=None,clinical_review_status=STATUS,
          provenance='Hand-authored synthetic lexical evaluation criterion; no clinical guideline approval',scope='consented_intake_symptoms',
          effective_at='2026-10-26',expires_at='2027-10-26',policy_version=POLICY,uncertainty='needs_clinician_review',referral_obligation='not_assessed',urgency='not_assessed')
        rule['digest']=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
        found.append({'rule':rule,'evidence':{'text':match.group(0),'start':match.start(),'end':match.end()}})
    return found

def urgent_notice(text):
    if not isinstance(text,str):return None
    # Notice asserts no classification; ambiguous/conditional reports may still show help.
    concern=re.search(r'навредить\s+себе|хочу\s+умереть|покончу\s+с\s+собой|убью\s+себя|непосредственная\s+опасность',unicodedata.normalize('NFKC',text),re.I)
    return dict(NOTICE) if concern else None
