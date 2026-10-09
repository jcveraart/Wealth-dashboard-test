"""Start with the demo; switch explicitly to your own separate data."""
import argparse
from profiles import launch
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['demo','personal'],nargs='?',default='demo');p.add_argument('--port',type=int);p.add_argument('--foreground',action='store_true');p.add_argument('--no-browser',action='store_true');p.add_argument('--reset-demo',action='store_true');p.add_argument('--command',choices=['start','stop','status','restart','autostart','disable-autostart'],default='start');a=p.parse_args()
    try:
        runtime,port=launch(a.mode,a.port,a.foreground,a.no_browser,a.reset_demo,a.command);print(f'{a.mode.title()} workspace: http://127.0.0.1:{port}\nData folder: {runtime.name}')
    except (OSError,RuntimeError,ValueError) as e:p.exit(1,str(e)+'\nSee docs/INSTALLATION.md.\n')
if __name__=='__main__':main()
