"""Reproducible allowlisted source ZIP; no runtime state, bundled archive or secret."""
import argparse,hashlib,json,os,stat,subprocess,zipfile
from pathlib import Path,PurePosixPath

TOP={'README.md','AGENTS.md','EVALUATION_POLICY_ADDENDUM.md','environment.yml','evaluation.config.example','alembic.ini','pytest.ini','pyproject.toml','package.json','Dockerfile','compose.yaml','.dockerignore','docker-compose.yml','docker-compose.yaml'}
DIRS={'backend','frontend','migrations','contracts','clinical_catalog_data','reference','tests','tests_ui','scripts','demo_completion','docker','tests_e2e','tests_perf','research_data'}
BLOCK_PARTS={'.git','.handoff','__pycache__','.pytest_cache','.ds_store','__macosx','node_modules','.ollama','models_cache','screenshots','before_after_screenshots','.ssh','.aws','.secrets','credentials'}
BLOCK_SUFFIXES=('.sqlite','.db','.sqlite-wal','.sqlite-shm','.db-wal','.db-shm','.sqlite-journal','.db-journal','.log','.pyc','.pyo','.key','.pem','.p12','.gguf','.safetensors','.onnx','.zip','.7z','.tar','.gz','.bak','.tmp','.har','.secret')
GUIDES={'EVALUATOR_QUICKSTART.md','EVALUATION_DEPLOYMENT.md','D01_D10_EVALUATION.md','UNRESOLVED_AND_PILOT_GATES.md','EVALUATION_ACCEPTANCE_SUMMARY.md','UX_REPAIR_2026_10_26.md','NEW_FRONTEND_INTEGRATION_AUDIT_2026_10_27.md','ROLE_JOURNEYS_AND_GUEST_HANDOFF_2026_10_27.md','AI_DEMO_GUIDE_2026_10_27.md','CODEX_PHASE0_PHASE1_PROMPT_2026_10_27.md','CODEX_JURY_RELEASE_PHASE0_PHASE3_PROMPT_2026_10_27.md','JURY_RELEASE_ACCEPTANCE.md','SUBAGENT_BUDGET_PROTOCOL.md','JURY_DEMO_RUNBOOK.md','DOCKER_JURY_RUNBOOK.md'}

def allowed(name):
    path=PurePosixPath(name);parts=path.parts
    if path.is_absolute() or '..' in parts or '\\' in name:return False
    lower=[x.casefold() for x in parts]
    if any(x in BLOCK_PARTS or x.startswith('.env') or x.startswith('credentials.') for x in lower):return False
    if lower[-1].endswith(BLOCK_SUFFIXES):return False
    if parts[0]=='backend' and len(parts)>1 and parts[1]=='data':return False
    if len(parts)==1:return name in TOP
    if name=='.codex/config.toml':return True
    if name in {'.agent/EXECPLAN_ACTIVE.md','.agent/CHECKPOINT.md'}:return True
    if parts[0] in DIRS:return True
    if parts[0]=='docs':
        return name=='docs/SCREEN_IMPLEMENTATION_MATRIX.csv' or (len(parts)==3 and parts[1]=='phase04' and parts[2] in GUIDES)
    return False

def validate_archive(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():raise ValueError('ZIP CRC failure')
        names=archive.namelist()
        if len({x.casefold() for x in names})!=len(names):raise ValueError('Duplicate/case-colliding archive paths')
        for item in archive.infolist():
            if item.filename!='PACKAGE_MANIFEST.json' and not allowed(item.filename):raise ValueError('Disallowed archive member: '+item.filename)
            if stat.S_ISLNK(item.external_attr>>16):raise ValueError('Symlink in archive')
            data=archive.read(item)
            if zipfile.is_zipfile(__import__('io').BytesIO(data)):raise ValueError('Nested archive detected')
        manifest=json.loads(archive.read('PACKAGE_MANIFEST.json'))
        if set(names)!={x['path'] for x in manifest['files']}|{'PACKAGE_MANIFEST.json'}:raise ValueError('Manifest mismatch')
        for item in manifest['files']:
            data=archive.read(item['path'])
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Checksum mismatch')
        return dict(status='PASS',provisional=manifest.get('provisional',True),files=len(names),source_commit=manifest['source_commit'],source_tree_sha256=manifest['source_tree_sha256'],zip_bytes=Path(path).stat().st_size,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),nested_archives=0,forbidden_members=0)

def build(root,target,working=False):
    root=Path(root).resolve();target=Path(target).resolve()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
    if working:tracked+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
    files=[]
    for name in sorted(set(n for n in tracked if n and allowed(n))):
        path=root/name
        if path.is_symlink() or not path.is_file():raise ValueError('Source must be ordinary file: '+name)
        data=path.read_bytes();files.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    dirty=bool(subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=root,text=True).strip())
    if dirty and not working:raise ValueError('Commit reviewed source before final organizer release; --include-working is provisional only')
    manifest=dict(product='Clinical Compass Evaluation MVP Phase04',source_commit=commit,provisional=working or dirty,
        source_tree_sha256=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),clinical_review_status='experimental_needs_validation',platform_verified='macOS Apple Silicon, existing cc-m1 and local Ollama',files=files)
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for item in files:
            path=root/item['path'];info=zipfile.ZipInfo(item['path'],date_time=(2026,10,26,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(0o100755 if os.access(path,os.X_OK) else 0o100644)<<16
            archive.writestr(info,path.read_bytes())
        info=zipfile.ZipInfo('PACKAGE_MANIFEST.json',date_time=(2026,10,26,0,0,0));info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(info,json.dumps(manifest,ensure_ascii=False,indent=2).encode())
    return validate_archive(target)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--include-working',action='store_true');p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    result=validate_archive(a.output) if a.verify_only else build(Path(__file__).resolve().parents[1],a.output,a.include_working)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
