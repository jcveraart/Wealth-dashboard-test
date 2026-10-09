"""Windows background launcher and tray controls; only manages this dashboard instance."""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'cache'
CONFIG=CACHE/'desktop.json'

def app_config():
    import app
    return app.PORT,app.HOSTNAME

def health():
    port,_=app_config()
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/workspace/health',timeout=2) as r:data=json.load(r)
        if data.get('instance')!=hashlib.sha256(str(ROOT).encode()).hexdigest()[:20]:return None
        return data
    except Exception:return None

def start(open_browser=True):
    CACHE.mkdir(exist_ok=True)
    status=health()
    if not status:
        executable=Path(sys.executable)
        if os.name=='nt' and (executable.parent/'pythonw.exe').is_file():executable=executable.parent/'pythonw.exe'
        flags=0
        if os.name=='nt':flags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_BREAKAWAY_FROM_JOB
        with (CACHE/'server-output.log').open('ab') as out,(CACHE/'server-error.log').open('ab') as err:
            try:p=subprocess.Popen([str(executable),'-X','utf8',str(ROOT/'app.py'),'--no-browser'],cwd=str(ROOT),stdout=out,stderr=err,creationflags=flags,start_new_session=os.name!='nt')
            except OSError:
                p=subprocess.Popen([str(executable),'-X','utf8',str(ROOT/'app.py'),'--no-browser'],cwd=str(ROOT),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
        for _ in range(40):
            status=health()
            if status:break
            if p.poll() is not None:raise RuntimeError('The dashboard could not start. Check cache/server-error.log; another application may already use this port.')
            time.sleep(.25)
        if not status:raise RuntimeError('The dashboard is still starting. Check the local server log.')
    console=Path(sys.executable)
    if os.name=='nt' and (console.parent/'python.exe').is_file():console=console.parent/'python.exe'
    CONFIG.write_text(json.dumps({'pid':status['pid'],'executable':str(console),'instance':status['instance'],'started':time.time()},indent=2),encoding='utf-8')
    if open_browser:open_site()
    return status

def stop():
    status=health()
    if not status:return {'stopped':False,'reason':'No verified dashboard instance is running.'}
    if status['pid']==os.getpid():raise RuntimeError('Cannot stop the controller itself.')
    os.kill(int(status['pid']),signal.SIGTERM)
    for _ in range(40):
        if not health():break
        time.sleep(.1)
    return {'stopped':True}

def open_site():
    port,host=app_config();webbrowser.open('http://'+host+(':'+str(port) if port!=80 else ''))

def startup_path():
    if os.name!='nt':raise RuntimeError('Automatic login startup is available on Windows.')
    return Path(os.environ['APPDATA'])/'Microsoft'/'Windows'/'Start Menu'/'Programs'/'Startup'/('Wealth Dashboard '+hashlib.sha256(str(ROOT).encode()).hexdigest()[:8]+'.lnk')

def autostart(enabled=True):
    path=startup_path()
    if not enabled:
        # Exact named shortcut only; never delete a directory or unrelated startup entry.
        if path.is_file():path.unlink()
        return {'enabled':False}
    exe=Path(sys.executable)
    if (exe.parent/'pythonw.exe').is_file():exe=exe.parent/'pythonw.exe'
    def quote(value):return "'"+str(value).replace("'","''")+"'"
    script="$s=(New-Object -ComObject WScript.Shell).CreateShortcut("+quote(path)+");$s.TargetPath="+quote(exe)+";$s.Arguments="+quote('-X utf8 "'+str(ROOT/'desktop.py')+'" tray --no-open')+";$s.WorkingDirectory="+quote(ROOT)+";$s.WindowStyle=7;$s.Description='Local wealth dashboard';$s.Save()"
    subprocess.run(['powershell','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-Command',script],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    return {'enabled':True,'shortcut':path.name}

def tray(open_browser=True):
    start(open_browser)
    if os.name!='nt':return
    # A named mutex prevents repeated launchers from creating multiple tray icons.
    import ctypes
    mutex_name='Local\\WealthDashboardTray-'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:20]
    ctypes.windll.kernel32.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    ctypes.windll.kernel32.CreateMutexW.restype=ctypes.c_void_p
    handle=ctypes.windll.kernel32.CreateMutexW(None,False,mutex_name)
    if ctypes.windll.kernel32.GetLastError()==183:return
    try:
        import pystray
        from PIL import Image,ImageDraw
        image=Image.new('RGBA',(64,64),(0,0,0,0));draw=ImageDraw.Draw(image);draw.rounded_rectangle((5,5,59,59),radius=15,fill='#2a78d6');draw.line([(16,20),(23,44),(32,29),(41,44),(48,20)],fill='white',width=5)
        def open_cb(icon,item):start(True)
        def restart_cb(icon,item):stop();start(False)
        def stop_cb(icon,item):stop();icon.stop()
        def exit_cb(icon,item):icon.stop()
        menu=pystray.Menu(pystray.MenuItem('Open dashboard',open_cb,default=True),pystray.MenuItem('Restart dashboard',restart_cb),pystray.MenuItem('Stop dashboard',stop_cb),pystray.MenuItem('Hide tray icon',exit_cb))
        pystray.Icon('WealthDashboard',image,'Wealth · local dashboard',menu).run()
    finally:
        ctypes.windll.kernel32.CloseHandle.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.CloseHandle(handle)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','restart','stop','status','tray','autostart','disable-autostart'],nargs='?',default='tray');p.add_argument('--no-open',action='store_true');args=p.parse_args()
    if args.action in ('start','tray'):
        if args.action=='tray':tray(not args.no_open)
        else:print(json.dumps(start(not args.no_open)))
    elif args.action=='restart':
        stop();print(json.dumps(start(not args.no_open)))
    elif args.action=='stop':print(json.dumps(stop()))
    elif args.action=='status':print(json.dumps(health() or {'ok':False}))
    else:print(json.dumps(autostart(args.action=='autostart')))

if __name__=='__main__':
    try:main()
    except Exception as e:
        CACHE.mkdir(exist_ok=True)
        with (CACHE/'launcher-error.log').open('a',encoding='utf-8') as f:f.write(str(e)+'\n')
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(e),'Wealth could not start',0x10)
        else:raise
