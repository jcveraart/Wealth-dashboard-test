"""Profile guardrails and local onboarding endpoints; demo never uses external services."""
import base64,json,os,subprocess,sys,threading,time,urllib.request
from pathlib import Path
from urllib.parse import urlparse
_installed=False
def install(app):
    global _installed
    if _installed:return
    _installed=True
    meta=json.loads((app.HERE/'runtime-profile.json').read_text());mode=meta['mode'];settings=app.load(app.SETTINGS,{})
    app.PORT=int(meta['port']);app.HOSTNAME='127.0.0.1'
    public=mode=='personal' and bool(settings.get('public_data_enabled'));ai_on=mode=='personal' and bool(settings.get('ai_enabled'));cloud_on=mode=='personal' and bool(settings.get('cloud_enabled'))
    if not public and '--offline' not in sys.argv:sys.argv.append('--offline')
    if not ai_on:
        app.api_key=lambda:None;app.ai_claude_code=lambda:None
        import spending,local
        local.models=lambda force=False:[]
        def unavailable(*a,**k):raise RuntimeError('AI is off in this profile. Use Setup & help in a personal workspace to enable it.')
        spending.run_ai=unavailable;local.run=unavailable
    if not cloud_on:app.cloud_config=lambda:None
    if mode=='demo':
        original_spending_line=app.spending_line
        app.spending_line=lambda result:original_spending_line(result).replace('Categorising the rest with AI in the background; check the To review tab on the Spending page.','Review the remaining example categories in To review. No AI request was made.')
        import providers,chatgpt_auth
        def status():return {'chat_provider':'claude','import_provider':'claude','has_openai_plan':False,'chatgpt':{'connected':False,'profiles':[],'active':None},'openai_chat_model':'','openai_import_model':''}
        providers.status=status;chatgpt_auth.status=lambda:{'connected':False,'profiles':[],'active':None}
        original_urlopen=urllib.request.urlopen
        def local_only(request,*a,**k):
            url=request.full_url if hasattr(request,'full_url') else str(request);target=urlparse(url)
            if target.hostname not in ('127.0.0.1','localhost') or target.port!=app.PORT:raise RuntimeError('External requests are disabled in the demo. Use a personal profile.')
            return original_urlopen(request,*a,**k)
        urllib.request.urlopen=local_only
    original_state=app.compute_state
    def state(cfg,record=True,include_intelligence=True):
        result=original_state(cfg,record,include_intelligence);result['status']['demo']=mode=='demo';result['status']['profile']=mode;return result
    app.compute_state=state
    get=app.Handler.extra_get;post=app.Handler.extra_post
    def extra_get(self,path,q):
        if path=='/api/setup/status':return self.send_json({'mode':mode,'public_data_enabled':public,'ai_enabled':ai_on,'cloud_enabled':cloud_on,'data_folder':app.HERE.name,'version':meta.get('version'),'guide':'/guide.html'})
        if mode=='demo' and path.startswith('/api/chatgpt/'):return self.send_json({'connected':False,'profiles':[],'active':None,'models':[]})
        return get(self,path,q)
    def extra_post(self,body):
        path=self.path
        if path=='/api/setup/personal':
            from profiles import prepare
            project=Path(meta['project_root']).resolve();runtime=prepare('personal',project=project)
            port=json.loads((runtime/'runtime-profile.json').read_text())['port']
            executable=project/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            if not executable.exists():executable=Path(sys.executable)
            subprocess.run([str(executable),'-X','utf8',str(runtime/'desktop.py'),'start','--no-open'],cwd=runtime,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            return self.send_json({'url':f'http://127.0.0.1:{port}/#setup','mode':'personal'})
        if path=='/api/setup/preferences':
            if mode!='personal':return self.send_json({'error':'Start your own personal workspace first.'},400)
            value=app.load(app.SETTINGS,{})
            for name in ('public_data_enabled','ai_enabled','cloud_enabled'):
                if name in body:
                    if type(body[name]) is not bool:return self.send_json({'error':'Choose an enabled or disabled option.'},400)
                    value[name]=body[name]
            app.save(app.SETTINGS,value)
            def restart():
                time.sleep(.5);subprocess.Popen([sys.executable,'-X','utf8',str(app.HERE/'desktop.py'),'restart','--no-open'],cwd=app.HERE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            threading.Thread(target=restart,daemon=True).start();return self.send_json({'ok':True,'restarting':True})
        if path=='/api/chat' and not ai_on:
            label='Saved demo reply — no AI request was made.' if mode=='demo' else 'AI is not enabled in this personal workspace yet.'
            return self.send_json({'reply':label+'\n\nExplore the account, investment and spending views. Use **Setup & help** to connect your chosen provider when you start with your own data.','level':'demo' if mode=='demo' else 'setup'})
        if mode=='demo':
            blocked=path.startswith('/api/chatgpt/') or path=='/api/settings' or path in ('/api/cloud','/api/cloud/sync','/api/news/picks','/api/opportunities/refresh','/api/intelligence/refresh','/api/intelligence/connections','/api/workspace/public','/api/workspace/source-updates','/api/workspace/source-update','/api/workspace/cloud-preview','/api/workspace/cloud-import','/api/workspace/feed-refresh')
            if blocked:return self.send_json({'error':'This demo stays disconnected. Open Setup & help → Use my own data to configure services.'},400)
            if path.startswith('/api/import') or path=='/api/workspace/intake':
                files=body.get('files',[]);valid=bool(files)
                for f in files:
                    try:raw=base64.b64decode(f.get('data','')).decode('utf-8');valid=valid and 'DEMO ONLY:' in raw
                    except Exception:valid=False
                if not valid:return self.send_json({'error':'Use the included demo sample CSV here. Start a personal workspace before importing real documents.'},400)
        if not public and path in ('/api/intelligence/refresh','/api/workspace/public','/api/workspace/feed-refresh'):return self.send_json({'error':'Enable public data in Setup & help first.'},400)
        return post(self,body)
    app.Handler.extra_get=extra_get;app.Handler.extra_post=extra_post
