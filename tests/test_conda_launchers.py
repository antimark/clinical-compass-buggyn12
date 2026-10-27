"""Conda handoff checks that do not require the Conda executable to be installed.

They inspect the environment declaration and capture launcher delegation via a
fake Conda executable. This is NOT a substitute for an actual Conda install.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_conda_environment_delegates_requirements_to_single_file():
    spec = yaml.safe_load((ROOT / 'environment.yml').read_text(encoding='utf-8'))
    assert spec['name'] == 'clinical-compass'
    assert 'conda-forge' in spec['channels']
    assert 'python=3.11' in spec['dependencies']
    assert 'nodejs=22' in spec['dependencies']
    assert 'pip' in spec['dependencies']
    pip_specs = [entry['pip'] for entry in spec['dependencies'] if isinstance(entry, dict) and 'pip' in entry]
    assert pip_specs == [['-r backend/requirements.txt']]
    assert (ROOT / 'backend/requirements.txt').is_file()


def test_all_entrypoints_run_inside_conda_instead_of_system_python():
    for name in ('start.sh', 'test.sh', 'start_windows.cmd', 'test_windows.cmd'):
        source = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
        assert 'conda run' in source.lower(), name
        assert 'CC_CONDA_ENV' in source, name
        assert 'venv' not in source.lower(), name
    for name in ('start_windows.cmd', 'test_windows.cmd'):
        source = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
        assert 'call conda run' in source.lower()  # conda may resolve to conda.bat
    assert 'conda env create -f environment.yml' in (ROOT / 'README.md').read_text(encoding='utf-8')


def _run_launcher_with_fake_conda(tmp_path, launcher, additional_env=None):
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    recorder = tmp_path / 'conda_invocations.jsonl'
    stub = fake_bin / 'conda'
    stub.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CC_FAKE_CONDA_LOG'], 'a', encoding='utf-8') as f:
    f.write(json.dumps({'args':sys.argv[1:], 'demo':os.environ.get('CC_DEMO_MODE'),
                        'db':os.environ.get('CC_DB_PATH'), 'key':os.environ.get('CC_SECRET_KEY'),
                        'pythonpath':os.environ.get('PYTHONPATH')}) + '\\n')
if os.environ.get('CC_FAKE_FAIL') == '1' and 'pytest' in sys.argv:
    sys.exit(29)
''', encoding='utf-8')
    stub.chmod(0o755)
    env = os.environ.copy()
    env.update({
        'PATH': str(fake_bin) + os.pathsep + env.get('PATH', ''),
        'CC_FAKE_CONDA_LOG': str(recorder),
        'CC_CONDA_ENV': 'test-clinical-compass',
        'CC_SECRET_KEY': 'SYNTHETIC_TEST_KEY_NO_REAL_SECRETS',
        'CC_DB_PATH': str(tmp_path / 'fake.sqlite'),
    })
    if additional_env:
        env.update(additional_env)
    result = subprocess.run(['bash', str(ROOT / 'scripts' / launcher)], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=15)
    records = [json.loads(x) for x in recorder.read_text().splitlines()] if recorder.exists() else []
    return result, records


@pytest.mark.skipif(not shutil.which('bash'), reason='POSIX launcher test requires bash')
def test_posix_demo_launcher_uses_expected_env_and_conda(tmp_path):
    result, records = _run_launcher_with_fake_conda(tmp_path, 'start.sh')
    assert result.returncode == 0, result.stderr
    assert len(records) == 1
    call = records[0]
    assert call['args'] == ['run', '--no-capture-output', '-n', 'test-clinical-compass',
                            'python', 'backend/run.py']
    assert call['demo'] == '1'
    assert call['key'] == 'SYNTHETIC_TEST_KEY_NO_REAL_SECRETS'
    assert call['pythonpath'].split(os.pathsep)[0] == str(ROOT / 'backend')


@pytest.mark.skipif(not shutil.which('bash'), reason='POSIX launcher test requires bash')
def test_posix_suite_uses_conda_for_python_node_and_stops_on_failure(tmp_path):
    result, records = _run_launcher_with_fake_conda(tmp_path, 'test.sh')
    assert result.returncode == 0, result.stderr
    assert len(records) == 4
    assert all(c['args'][:4] == ['run', '--no-capture-output', '-n', 'test-clinical-compass']
               for c in records)
    assert [c['args'][4] for c in records] == ['python', 'python', 'node', 'node']
    assert 'pytest' in records[1]['args']
    faildir = tmp_path / 'failcase'
    faildir.mkdir()
    result2, records2 = _run_launcher_with_fake_conda(faildir, 'test.sh', {'CC_FAKE_FAIL': '1'})
    assert result2.returncode == 29
    assert len(records2) == 2  # compileall ran, pytest failed; Node was not launched
