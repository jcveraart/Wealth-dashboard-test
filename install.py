"""Install optional live-data, document and AI features in this project's own virtual environment."""
import os,subprocess,sys,venv
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    if sys.version_info<(3,10):raise SystemExit('Install Python 3.11 or 3.12 for optional features. The offline demo supports Python 3.9+.')
    env=ROOT/'.venv'
    if not env.exists():venv.EnvBuilder(with_pip=True).create(env)
    python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
    print('Optional features installed. Start personal.py, then choose connections in Setup & help.')
if __name__=='__main__':main()
