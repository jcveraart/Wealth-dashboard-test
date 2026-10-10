"""Isolated runtime preparation; updates copy source, never someone else's records."""
import json,os,shutil,subprocess,sys,uuid
from datetime import date,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODES={'demo':('.demo-runtime',8051),'personal':('.personal-runtime',8052)}
def read(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default
def inside(path,root):
    path=Path(path).resolve();root=Path(root).resolve()
    if path==root or root not in path.parents:raise RuntimeError('The runtime must stay inside its project folder.')
    return path
def source_files(root=ROOT):
    names=set(read(root/'release.json',{}).get('source_files',[]))|{'profile_setup.py','profiles.py','launch.py','personal.py','demo.py','generate_demo.py','demo_extras.py','release.json','web/countries.json'}
    for p in (root/'web').rglob('*'):
        if p.is_file() and p.suffix.lower() in ('.js','.css','.html','.png','.jpg','.jpeg','.svg','.csv','.txt'):names.add(p.relative_to(root).as_posix())
    names.update(p.relative_to(root).as_posix() for p in (root/'docs').rglob('*') if p.is_file() and p.suffix.lower() in ('.md','.png','.jpg'))
    names.update(n for n in ('README.md','install.py','start-demo-windows.bat','start-personal-windows.bat','start-windows.bat','start-mac.command','start-demo-mac.command','start-demo-linux.sh','start-personal-mac.command','start-personal-linux.sh','install-optional-windows.bat','stop-demo-windows.bat','stop-personal-windows.bat') if (root/n).is_file())
    return sorted(n for n in names if (root/n).is_file() and not n.startswith(('demo_data/','tests/')))
def copy_code(destination,source=ROOT):
    for name in source_files(source):
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('Unsafe source manifest')
        target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/rel,target)
def empty_personal(root):
    cfg={'accounts':[],'managed':{'name':'Managed portfolio (not set up)','value_eur':0,'value_date':date.today().isoformat(),'profit_at_value_date_eur':0,'start_value_eur':0,'start_date':date.today().isoformat(),'fees_paid_eur':0,'positions':[],'proxy':[],'cash_eur':0},'savings':[],'debts':[],'profile':{},'goals':[],'pots':[],'savings_plans':[],'watchlist':[],'todos':[],'account_history':[],'yearly_flows':[],'refresh_minutes':5}
    def write(name,value):(root/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    write('portfolio.json',cfg);write('settings.json',{'public_data_enabled':False,'ai_enabled':False});write('receipts.json',{'version':1,'documents':[]});write('chats.json',[]);write('ui.json',{'prefs':{'local_ai':'off'}})
    for name in ('inbox.json','imports.json'):write(name,[])
    (root/'notes.md').write_text('# My dashboard\n\nAdd confirmed information about your goals and accounts here.\n',encoding='utf-8')
    (root/'history.csv').write_text('date,net_worth,gross,managed,savings,self_directed,debt,etf,stocks,bonds,other_inv,cash,invest_profit\n',encoding='utf-8');(root/'history_accounts.csv').write_text('date,account,value\n',encoding='utf-8')
def prepare(mode='demo',reset=False,project=ROOT,runtime=None):
    if mode not in MODES:raise ValueError('Choose demo or personal')
    if reset and mode!='demo':raise ValueError('Personal data is never reset by the demo launcher.')
    project=Path(project).resolve();runtime=inside(runtime or project/MODES[mode][0],project)
    meta=read(runtime/'runtime-profile.json',{});legacy=read(runtime/'manifest.json',{})
    if runtime.exists():
        valid=meta.get('mode')==mode or mode=='demo' and legacy.get('synthetic') is True
        if not valid and mode=='personal':raise RuntimeError('An unmarked personal folder exists. Its contents were left unchanged. Move it aside before creating a fresh profile.')
        if valid and not reset:
            copy_code(runtime,project);(runtime/'runtime-profile.json').write_text(json.dumps({'mode':mode,'project_root':str(project),'version':read(project/'release.json',{}).get('version'),'port':meta.get('port',MODES[mode][1])},indent=2),encoding='utf-8');return runtime
    pending=inside(project/('.'+mode+'-runtime-init-'+uuid.uuid4().hex),project);pending.mkdir();copy_code(pending,project)
    if mode=='demo':
        from generate_demo import generate
        generate(pending)
        from demo_extras import enrich
        enrich(pending)
    else:empty_personal(pending)
    (pending/'runtime-profile.json').write_text(json.dumps({'mode':mode,'project_root':str(project),'version':read(project/'release.json',{}).get('version'),'port':MODES[mode][1]},indent=2),encoding='utf-8')
    if runtime.exists():
        backup=inside(project/'backups'/('demo-preserved-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')),project);backup.parent.mkdir(parents=True,exist_ok=True);runtime.rename(backup);print('Previous demo preserved in',backup.relative_to(project))
    pending.rename(runtime);return runtime
def launch(mode='demo',port=None,foreground=False,no_browser=False,reset=False,command='start'):
    runtime=prepare(mode,reset);meta=read(runtime/'runtime-profile.json',{});port=port or meta.get('port') or MODES[mode][1]
    if not 1024<=port<=65535:raise ValueError('Use a local port between 1024 and 65535.')
    meta['port']=port;(runtime/'runtime-profile.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    executable=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not executable.is_file():executable=Path(sys.executable)
    args=[str(executable),'-X','utf8',str(runtime/('app.py' if foreground else 'desktop.py'))]
    args+=(['--no-browser'] if no_browser else []) if foreground else [command]+(['--no-open'] if no_browser and command in ('start','restart','tray') else [])
    if subprocess.run(args,cwd=runtime).returncode:raise RuntimeError('The profile could not start. Check its cache/server-error.log and docs/INSTALLATION.md.')
    return runtime,port
