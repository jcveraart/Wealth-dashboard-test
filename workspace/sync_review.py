"""Read-only comparisons for the existing cloud copy and source repository."""
import json,os,shutil,subprocess
from pathlib import Path
from . import service,store

def compare(local,remote):
    rows=[]
    for section in sorted(set(local)|set(remote)):
        a,b=local.get(section),remote.get(section)
        if a==b:continue
        rows.append({'section':section,'local_records':len(a) if isinstance(a,(list,dict)) else 1 if a is not None else 0,
          'cloud_records':len(b) if isinstance(b,(list,dict)) else 1 if b is not None else 0,'status':'Different' if section in local and section in remote else 'Local only' if section in local else 'Cloud only'})
    return rows

def cloud_preview():
    import app,cloud
    config=app.cloud_config()
    if not config:return {'configured':False,'differences':[],'scope':'Connect your own Supabase project in existing settings to compare its saved portfolio copy.'}
    url,key=config
    rows=cloud._request(url,key,'GET','portfolio_backup?id=eq.1&select=data,updated_at&limit=1')
    if not rows:return {'configured':True,'differences':[],'scope':'No saved portfolio cloud copy exists yet.'}
    remote=rows[0]['data']
    if not isinstance(remote,dict):raise ValueError('The saved cloud portfolio is not a supported object.')
    differences=compare(service.cfg(),remote)
    return {'configured':True,'updated_at':rows[0].get('updated_at'),'differences':differences,'identical':not differences,'scope':'Read-only comparison of portfolio.json with the existing Supabase portfolio backup. Does not merge, upload or replace either copy. Workspace planning records and original attachments remain local and are covered by the complete encrypted backup.'}

def updates(fetch=False):
    git=shutil.which('git')
    if not git or not (store.ROOT/'.git').exists():return {'available':False,'scope':'Update checks require the original Git checkout; a downloaded ZIP has no Git history. Download a newer source archive and retain your separate private data.'}
    env={**os.environ,'GIT_TERMINAL_PROMPT':'0'}
    def run(*args):
        result=subprocess.run([git,'-C',str(store.ROOT),*args],env=env,capture_output=True,text=True,encoding='utf-8',timeout=35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError('The source repository could not complete this check. Verify the saved Git remote and GitHub sign-in.')
        return result.stdout.strip()
    current=run('branch','--show-current')
    if not current:return {'available':True,'scope':'This checkout is detached. Select its intended branch before updating.'}
    if fetch:run('fetch','origin','--prune')
    remote='origin/'+current
    try:
        ahead,behind=map(int,run('rev-list','--left-right','--count','HEAD...'+remote).split())
    except ValueError:return {'available':True,'branch':current,'scope':'No matching remote branch is available yet.'}
    modified=run('status','--porcelain','--untracked-files=no').splitlines()
    changed=run('diff','--name-only','HEAD...'+remote).splitlines()
    return {'available':True,'branch':current,'commit':run('rev-parse','--short','HEAD'),'ahead':ahead,'behind':behind,'modified_count':len(modified),'changed_files':changed[:100],
      'scope':'Source update preview only. Local data and settings are Git-ignored. No merge is performed; review local source edits and make a complete backup before applying an update.'}
