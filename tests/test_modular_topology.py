"""No-Flask static guard for the refactored source package."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'backend' / 'cc_api'


def test_app_factory_is_public_and_modular():
    public = (API / '__init__.py').read_text(encoding='utf-8')
    assert 'from .app import create_app' in public
    for name in ('app.py', 'config.py', 'database.py', 'demo_fixtures.py',
                 'http_hooks.py', 'core_routes.py', 'feature_registry.py', 'utilities.py'):
        ast.parse((API / name).read_text(encoding='utf-8'))


def test_original_schema_and_frontend_location_retained():
    assert (ROOT / 'migrations' / 'versions').is_dir()
    assert (ROOT / 'frontend' / 'dist' / 'index.html').is_file()
    assert '*.sqlite' in (ROOT / '.gitignore').read_text(encoding='utf-8')


def test_all_js_suites_are_collected_in_mac_launcher():
    source = (ROOT/'scripts'/'test.sh').read_text(encoding='utf-8')
    assert 'node --test frontend/dist/tests/*.cjs' in source
