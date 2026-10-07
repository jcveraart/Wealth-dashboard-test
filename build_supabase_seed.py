"""Assemble the synthetic SQL chunks for a new, empty Supabase demo project. No connections are made."""
from pathlib import Path
root = Path(__file__).absolute().parent
pieces = sorted((root / 'demo_data/sql').glob('*.sql'))
if not pieces:
    raise SystemExit('No synthetic SQL chunks found.')
output = root / 'cache/demo-supabase-seed.sql'
output.parent.mkdir(exist_ok=True)
output.write_text('-- SYNTHETIC DATA ONLY: use a new, empty demo project.\n\n' +
                  '\n\n'.join(p.read_text(encoding='utf-8') for p in pieces), encoding='utf-8')
print('Synthetic seed written to', output)
print('After the four schema files, paste this SQL into your new demo project SQL Editor.')
