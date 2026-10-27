"""Run with -p tests_e2e.pytest_evidence to flush each completed source test."""
from tests_e2e.evidence import record
def pytest_runtest_logreport(report):
    if report.when == 'call' or report.when == 'setup' and report.outcome != 'passed':
        state={'passed':'PASS','failed':'FAIL','skipped':'SKIP'}[report.outcome]
        record(report.nodeid,state,report.duration,method='live Flask + SQLite + Chromium' if report.nodeid.startswith('tests_e2e/test_') else 'source pytest; not live E2E', detail='xfail' if hasattr(report,'wasxfail') else '')
