"""Launch the unchanged dashboard with isolated synthetic data. Python 3.9+; no packages needed offline."""
import argparse
import json
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).absolute().parent
RUNTIME = ROOT / '.demo-runtime'
MODULES = ['app.py', 'ai.py', 'cloud.py', 'db.py', 'extras.py', 'ideas.py', 'local.py', 'public.py', 'spending.py']
DATA_FILES = ['portfolio.json', 'spending.json', 'notes.md', 'history.csv', 'history_accounts.csv',
              'inbox.json', 'imports.json', 'ui.json', 'chats.json', 'settings.json']

def copy_code(destination):
    for name in MODULES + ['DATA.md']:
        shutil.copy2(ROOT / name, destination / name)
    # Offline mode needs no packages; a missing optional dependency list must not prevent it.
    if (ROOT / 'requirements.txt').is_file():
        shutil.copy2(ROOT / 'requirements.txt', destination / 'requirements.txt')
    shutil.copytree(ROOT / 'web', destination / 'web', dirs_exist_ok=True)

def prepare(reset=False):
    marker = RUNTIME / 'manifest.json'
    if marker.exists():
        metadata = json.loads(marker.read_text(encoding='utf-8'))
        if metadata.get('synthetic') is not True:
            raise RuntimeError('This runtime is not marked as a synthetic demo. Its files were left unchanged.')
        if not reset:
            copy_code(RUNTIME)
            return RUNTIME

    # Build a complete runtime before switching it into place. A failed first launch can be retried.
    pending = ROOT / ('.demo-runtime-init-' + uuid.uuid4().hex)
    pending.mkdir()
    copy_code(pending)
    from generate_demo import generate
    generate(pending)
    if RUNTIME.exists():
        backup = ROOT / 'backups' / ('demo-recovered-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        project = ROOT.resolve()
        source, destination = RUNTIME.resolve(), backup.resolve()
        if not source.is_relative_to(project) or not destination.is_relative_to(project):
            raise RuntimeError('The runtime or backup points outside this demo folder. Existing files were left unchanged.')
        backup.parent.mkdir(exist_ok=True)
        RUNTIME.rename(backup)
        print('Previous demo folder preserved at', backup)
    pending.rename(RUNTIME)
    return RUNTIME

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8051, help='Local port; default 8051 so the personal dashboard is untouched')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--reset', action='store_true', help='Back up demo edits, then regenerate the synthetic data')
    parser.add_argument('--live-prices', action='store_true', help='Optional Yahoo prices; requires requirements.txt packages')
    parser.add_argument('--connect-services', action='store_true', help='Allow separately configured AI, Ollama and Supabase for this demo')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use a port between 1024 and 65535.')
    runtime = prepare(args.reset)
    sys.path.insert(0, str(runtime))
    import app
    app.PORT, app.HOSTNAME = args.port, '127.0.0.1'
    if not args.connect_services:
        app.api_key = lambda: None
        app.ai_claude_code = lambda: None
        app.cloud_config = lambda: None
        import local
        local.models = lambda force=False: []
    original_state = app.compute_state
    def demo_state(cfg, record=True):
        state = original_state(cfg, record)
        state['status']['demo'] = not args.live_prices
        return state
    app.compute_state = demo_state
    sys.argv = ['app.py'] + ([] if args.live_prices else ['--offline']) + (['--no-browser'] if args.no_browser else [])
    print('WEALTH DEMO: invented accounts, payments and prices. Data is kept in .demo-runtime.')
    print('AI and Supabase are off unless --connect-services is supplied.')
    try:
        app.main()
    except OSError as e:
        if getattr(e, 'errno', None) in (48, 98, 10048) or getattr(e, 'winerror', None) == 10048:
            parser.exit(1, 'That demo port is already in use. Try: python demo.py --port 8052\n')
        raise

if __name__ == '__main__':
    main()
