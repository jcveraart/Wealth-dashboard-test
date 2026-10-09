"""Backward-compatible demo launcher. Personal data stays in a separate profile."""
import argparse
from profiles import ROOT,prepare as prepare_profile,launch
RUNTIME=ROOT/'.demo-runtime'
def prepare(reset=False):return prepare_profile('demo',reset,ROOT,RUNTIME)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8051);p.add_argument('--no-browser',action='store_true');p.add_argument('--foreground',action='store_true');p.add_argument('--reset',action='store_true');a=p.parse_args()
    try:launch('demo',a.port,a.foreground,a.no_browser,a.reset)
    except (OSError,ValueError,RuntimeError) as e:p.exit(1,str(e)+'\nSee docs/INSTALLATION.md.\n')
if __name__=='__main__':main()
