"""Thread context policy helpers; thread namespaces must never be merged."""
THREAD_TYPES=frozenset(('previsit','patient_doctor','doctor_peer'))

def pair_thread_key(a,b):
    if not a or not b or a==b:
        raise ValueError('Two distinct participants required')
    return ':'.join(sorted((a,b)))
