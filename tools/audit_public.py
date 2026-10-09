"""Audit files that Git would publish. Does not print matched credential values."""
import json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).absolute().parent.parent
names=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-c','-o','--exclude-standard'],text=True).splitlines()
errors=[]
private=('portfolio.json','spending.json','settings.json','receipts.json','history.csv','history_accounts.csv','chats.json','ui.json','notes.md','inbox.json','imports.json','runtime-profile.json')
for name in sorted(set(names)):
    p=ROOT/name
    if not p.is_file():continue
    if name in private or name.startswith(('.demo-runtime/','.personal-runtime/','.chatgpt/','cache/','backups/','attachments/')) or p.suffix.lower() in ('.sqlite3','.db','.wealthbackup'):errors.append(name+': runtime data path')
    if p.suffix.lower() in ('.png','.jpg','.jpeg'):continue
    try:text=p.read_text(encoding='utf-8-sig')
    except UnicodeError:errors.append(name+': unexpected binary');continue
    if re.search(r'(?:sk-(?:proj|ant|svcacct)-|sb_secret_)[A-Za-z0-9_-]{20,}',text):errors.append(name+': possible credential')
    if re.search(r'(?:C:[\\/]+Users[\\/]+Jan|jcveraart/wealth-dashboard(?:\.git|["\s]))',text,re.I):errors.append(name+': private owner/source reference')
    if re.search(r'\b[A-Z]{2}\d{2}[A-Z]{4}\d{10}\b',text) and not name.startswith('tests/'):errors.append(name+': possible account number')
if not json.loads((ROOT/'demo_data/manifest.json').read_text())['synthetic']:errors.append('Fixtures are not marked synthetic')
if errors:print('\n'.join(errors));sys.exit(1)
print('Public file audit passed: no runtime paths, account numbers, owner paths or credential patterns.')
