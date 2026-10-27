"""Inventory original source routes, API operations, forms and commands without running code.
Combine with Phase 0 live control observations; never infer E2E from code presence.
"""
import argparse,ast,csv,hashlib,io,json,re,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def apis(files):
    result={}
    for name,source in files.items():
        if not name.startswith('backend/cc_api/') or not name.endswith('.py'):continue
        try:tree=ast.parse(source)
        except SyntaxError:continue
        constants={}
        for node in tree.body:
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                for target in node.targets:
                    if isinstance(target,ast.Name):constants[target.id]=node.value.value
        def value(node):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
            if isinstance(node,ast.Name):return constants.get(node.id)
            if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):
                a,b=value(node.left),value(node.right)
                if a is not None and b is not None:return a+b
        for node in ast.walk(tree):
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            for decorator in node.decorator_list:
                if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute) and decorator.args:
                    method=decorator.func.attr;path=value(decorator.args[0])
                    if method in ('get','post','put','patch','delete') and path and path.startswith('/api/v1/'):
                        result[(method.upper(),path)]=name+':'+str(node.lineno)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',required=True);a=p.parse_args();original=Path(a.baseline)
    with zipfile.ZipFile(original) as archive:
        names=archive.namelist();route_name=next(n for n in names if n.endswith('frontend/dist/assets/data/routes.json'));prefix=route_name[:-len('frontend/dist/assets/data/routes.json')]
        baseline={n[len(prefix):]:archive.read(n).decode('utf-8') for n in names if n.startswith(prefix) and (n.endswith('.py') or n.endswith('.js') or n.endswith('routes.json') or n.endswith('INTEGRATION_MATRIX.csv'))}
    current={str(p.relative_to(ROOT)):p.read_text() for folder in ('backend/cc_api','frontend/dist/assets/js') for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.js')}
    routes=json.loads(baseline['frontend/dist/assets/data/routes.json']);now_routes=json.loads((ROOT/'frontend/dist/assets/data/routes.json').read_text())
    old_api=apis(baseline);now_api=apis(current)
    declared={row['path'] for row in now_routes};missing_routes=[r['path'] for r in routes if r['path'] not in declared]
    missing_api=[method+' '+path for method,path in old_api if (method,path) not in now_api]
    integration=list(csv.DictReader(io.StringIO(baseline['frontend/INTEGRATION_MATRIX.csv'].lstrip('\ufeff'))))
    integration={row['Маршрут']:row for row in integration}
    live={row['route']:row for row in csv.DictReader((ROOT/'reports/phase0/ROUTE_CONTROL_MATRIX.csv').open())}
    fields=['feature_id','role','route','action','baseline_status','final_status','test_result','evidence','notes'];rows=[]
    def add(role,route,action,status,present,evidence,notes='',test='NOT_RUN'):
        key=role+'|'+route+'|'+action
        rows.append(dict(feature_id=hashlib.sha256(key.encode()).hexdigest()[:16],role=role,route=route,action=action,baseline_status=status,final_status='PRESENT; Phase 2/3 pending' if present else 'REGRESSION: source missing',test_result=test,evidence=evidence,notes=notes))
    for route in routes:
        path=route['path'];status=integration.get(path,{}).get('Состояние UI','source-declared; live unverified')
        add(route['role'],path,route.get('action','render'),status,path in declared,'reports/phase0/ROUTE_CONTROL_MATRIX.csv','Original 102-route registry; rendering does not prove action completion',live.get(path,{}).get('status','NOT_RUN'))
    for (method,path),source in old_api.items():
        add('server_authorized',path,method,'implemented in original source; live unverified',(method,path) in now_api,now_api.get((method,path),source),'Server RBAC/tenant/consent unchanged; role is decided by actual endpoint guard')
    old_js='\n'.join(v for k,v in baseline.items() if k.startswith('frontend/dist/assets/js/') and k.endswith('.js'))
    now_js='\n'.join(v for k,v in current.items() if k.endswith('.js'))
    for attr in ('command','form'):
        for name in sorted(set(re.findall('data-'+attr+r'=["\x27]([a-z][a-z0-9-]*)["\x27]',old_js))):
            present=bool(re.search('data-'+attr+r'=["\x27]'+re.escape(name)+r'["\x27]',now_js))
            add('role_scoped','*',attr+':'+name,'visible control declared in original source',present,'reports/phase0/raw/controls.jsonl','Individual DOM instances below bind controls to routes; source presence is not action proof')
    observed=ROOT/'reports/phase0/raw/controls.jsonl'
    if observed.exists():
        seen=set()
        for line in observed.read_text().splitlines():
            batch=json.loads(line)
            for control in batch['controls']:
                action=control.get('command') or control.get('form') or control.get('href') or control['tag']+':'+control['label']
                key=(batch['role'],batch['route'],action)
                if key in seen:continue
                seen.add(key)
                add(*key,'Phase 0 visible DOM control',True,'reports/phase0/raw/controls.jsonl','Disabled='+str(control['disabled'])+'; label='+control['label'],'INVENTORIED; action NOT_RUN unless linked to specific E2E')
    out=ROOT/'reports/phase2/FEATURE_PARITY.csv';out.parent.mkdir(exist_ok=True)
    with out.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    summary=dict(baseline_archive=original.name,baseline_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),baseline_routes=len(routes),current_routes=len(now_routes),baseline_api_operations=len(old_api),current_api_operations=len(now_api),registry_rows=len(rows),missing_routes=missing_routes,missing_api=missing_api,phase2_status='NOT_RUN',phase3_status='NOT_RUN')
    (ROOT/'reports/phase0/raw/feature-parity-baseline.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    if missing_routes or missing_api:raise SystemExit(1)
if __name__=='__main__':main()
