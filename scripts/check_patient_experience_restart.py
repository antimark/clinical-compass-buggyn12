"""Disposable synthetic HTTP/process-restart acceptance; never targets an existing DB."""
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PX = '/api/v1/patient-experience'
OB = '/api/v1/onboarding'


def main():
    with tempfile.TemporaryDirectory(prefix='cc_phase3_restart_') as folder:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = dict(os.environ, CC_DEMO_MODE='1', CC_APP_ENV='synthetic_dev',
                   CC_SEED_PATIENT_PERSONAS='1', CC_AI_MODE='disabled', CC_PORT=str(port),
                   CC_SECRET_KEY='DISPOSABLE_SYNTHETIC_RESTART_CHECK_ONLY',
                   CC_DB_PATH=str(Path(folder) / 'restart.sqlite'), CC_PUBLIC_BASE_URL=base)
        env.pop('CC_DATABASE_URL', None)
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        process = None

        def request(path, method='GET', payload=None):
            headers = {'Content-Type': 'application/json'}
            if method != 'GET':
                headers['X-CSRF-Token'] = request(OB + '/bootstrap')['csrf_token']
            data = json.dumps(payload).encode() if payload is not None else None
            req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
            with client.open(req, timeout=10) as response:
                return json.load(response)

        def stop():
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        def start():
            proc = subprocess.Popen([sys.executable, 'backend/run.py'], cwd=ROOT,
                                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError('Disposable Flask process failed to start')
                try:
                    request('/api/v1/health')
                    return proc
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(.1)
            proc.terminate()
            proc.wait(timeout=5)
            raise RuntimeError('Disposable Flask startup timeout')

        try:
            process = start()
            login = {'email': 'trend_one@demo.test', 'password': 'Synthetic-demo-pass-42'}
            request(OB + '/login', 'POST', login)
            original = request(PX + '/observations')['series']
            assert original[0]['point_count'] == 1
            request(PX + '/observations', 'POST', {'metric_key': 'wellbeing', 'unit': 'points',
                    'scale_version': 'mood_1_5_v1', 'value': 4, 'event_key': 'actual-process-restart'})
            assignment = request(PX + '/questionnaires/assignments')['items'][0]
            endpoint = PX + '/questionnaires/assignments/' + assignment['id']
            draft = request(endpoint)['draft']
            request(endpoint + '/draft', 'PUT', {'definition_version': '1', 'revision': draft['revision'],
                    'answers': {'q1': 4}, 'last_page': 0})
            observations = request(PX + '/observations')
            draft = request(endpoint)['draft']
            assert observations['series'][0]['point_count'] == 2
            stop()
            process = start()
            # Retained real session cookie must resolve through persisted LocalAuthSession.
            assert request(PX + '/observations') == observations
            assert request(endpoint)['draft'] == draft
            request(OB + '/logout', 'POST', {})
            request(OB + '/login', 'POST', login)
            assert request(PX + '/observations') == observations
            assert request(endpoint)['draft'] == draft
            print('PASS: actual Flask process restart, persisted session, 1->2 observations, acknowledged draft and logout/login.')
            print('Temporary SQLite only. PostgreSQL/Keycloak NOT_RUN.')
        finally:
            stop()


if __name__ == '__main__':
    main()
