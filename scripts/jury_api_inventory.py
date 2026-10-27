"""Actual Flask URL map in a new disposable private workspace; no personal DB or model call."""
import csv,json,tempfile
from pathlib import Path
from cc_api import create_app
from cc_api.evaluation_launcher import workspace_config
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cc-jury-route-map-') as folder:
    app=create_app(workspace_config(folder))
    try:
        rows=[]
        for rule in app.url_map.iter_rules():
            if rule.rule.startswith('/api/v1/'):
                for method in sorted(rule.methods-{'HEAD','OPTIONS'}):rows.append({'method':method,'route':rule.rule,'endpoint':rule.endpoint,'authorization':'Actual server role/organization/consent guard; no inferred grant'})
        target=ROOT/'reports/phase2/API_REGISTRY.csv'
        with target.open('w') as f:w=csv.DictWriter(f,fieldnames=['method','route','endpoint','authorization']);w.writeheader();w.writerows(sorted(rows,key=lambda r:(r['route'],r['method'])))
        print(json.dumps({'actual_api_operations':len(rows),'unique_paths':len({r['route'] for r in rows}),'source':'actual Flask url_map; implicit HEAD/OPTIONS excluded','model_requests':0}))
    finally:
        app.extensions['safety_runtime'].close();app.extensions['cc_session_factory'].kw['bind'].dispose()
