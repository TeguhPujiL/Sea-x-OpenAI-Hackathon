"""Run the real dev frontend and FastAPI on one port, locally or in Codespaces."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.runtime'
PYTHON=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def environment():
    RUNTIME.mkdir(exist_ok=True)
    identity=RUNTIME/'demo-actor.json'
    if not identity.exists(): identity.write_text(json.dumps({'actor_id':str(uuid4())}),encoding='utf-8')
    actor=json.loads(identity.read_text(encoding='utf-8'))['actor_id']
    env=os.environ.copy()
    env.setdefault('PROCUREMIND_DATABASE_URL','sqlite:///'+(RUNTIME/'demo.db').as_posix())
    env.setdefault('PROCUREMIND_STORAGE_ROOT',str(RUNTIME/'pdfs'))
    env.setdefault('PROCUREMIND_DEMO_MODE','true')
    env.setdefault('PROCUREMIND_DEMO_ACTOR_ID',actor)
    env.setdefault('PROCUREMIND_DEMO_ROLE','REVIEWER')
    env.setdefault('PROCUREMIND_DEMO_DISPLAY_NAME','Public Demo Reviewer')
    contract=json.loads((ROOT/'docs/contract_snapshot.json').read_text(encoding='utf-8'))
    env.setdefault('PROCUREMIND_DEMO_SCOPES',json.dumps(sorted({e['scope'] for e in contract['endpoints']})))
    return env


def run(args,env=None,cwd=ROOT):
    subprocess.run([str(a) for a in args],cwd=cwd,env=env,check=True)


def npm():
    node=shutil.which('node')
    if not node:
        node=next((ROOT/'.tools').glob('node-*-win-x64/node.exe'),None)
    if not node: raise RuntimeError('Node.js is required')
    node=Path(node)
    if os.name=='nt': return [node,node.parent/'node_modules/npm/bin/npm-cli.js']
    binary=shutil.which('npm')
    if not binary: raise RuntimeError('npm is required')
    return [binary]


def setup(skip_install=False):
    env=environment()
    if os.name=="nt": env["PATH"]=str(Path(npm()[0]).parent)+os.pathsep+env.get("PATH","")
    if not PYTHON.exists(): run([sys.executable,'-m','venv',ROOT/'.venv'])
    if not skip_install:
        run([PYTHON,'-m','pip','install','-e',str(ROOT/'backend')],env)
        run([*npm(),'ci'],env,ROOT/'frontend')
    frontend_env={**env,'VITE_API_BASE_URL':'/api/v1'}
    run([*npm(),'run','build'],frontend_env,ROOT/'frontend')
    run([PYTHON,'-m','app.core.demo_bootstrap'],env)
    print('Demo setup complete; real backend and built frontend, no seeded findings or AI fallback.')


def start(foreground=False):
    env=environment()
    args=[str(PYTHON),'-m','uvicorn','app.web:create_web_app','--factory','--host','0.0.0.0','--port','8000']
    if foreground:
        run(args,env)
        return
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=1) as response:
            if response.status==200:
                print('Already running: http://127.0.0.1:8000')
                return
    except OSError: pass
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
    with (RUNTIME/'server.log').open('ab') as log:
        process=subprocess.Popen(args,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,**options)
    (RUNTIME/'server.pid').write_text(str(process.pid),encoding='utf-8')
    print('Started ProcureMind: http://127.0.0.1:8000')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['setup','start'])
    parser.add_argument('--skip-install',action='store_true')
    parser.add_argument('--foreground',action='store_true')
    args=parser.parse_args()
    setup(args.skip_install) if args.action=='setup' else start(args.foreground)
