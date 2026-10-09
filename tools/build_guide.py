import html,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
parts=[]
def table_markup(out):
    result=[];table=[];numbered=False
    def flush():
        if not table:return
        rows=[line.strip().strip('|').split('|') for line in table]
        result.append('<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+x.strip()+'</th>' for x in rows[0])+'</tr></thead><tbody>')
        for row in rows[2:]:result.append('<tr>'+''.join('<td>'+x.strip()+'</td>' for x in row)+'</tr>')
        result.append('</tbody></table></div>');table.clear()
    for item in out:
        if item.startswith('<p>|'):
            table.append(item[3:-4]);continue
        flush()
        match=re.match(r'<p>(?:\d+\. |[-] )(.*)</p>',item)
        if match:
            if not numbered:result.append('<ul>');numbered=True
            result.append('<li>'+match[1]+'</li>');continue
        if numbered:result.append('</ul>');numbered=False
        result.append(item)
    flush()
    if numbered:result.append('</ul>')
    return result

for name in ('INSTALLATION','CONNECTIONS','SCREENSHOTS'):
    source=(R/'docs'/f'{name}.md').read_text(encoding='utf-8');lines=source.splitlines();out=[];code=False
    for line in lines:
        if line.startswith('```'):
            out.append('</code></pre>' if code else '<pre><code>');code=not code;continue
        if code:out.append(html.escape(line)+'\n');continue
        if line.startswith('<!--'):continue
        text=html.escape(line)
        text=re.sub(r'!\[([^\]]*)\]\(([^)]*)\)',lambda m:'<img loading="lazy" alt="'+m[1]+'" src="'+m[2].replace('screenshots/','guide-images/')+'">',text)
        text=re.sub(r'\[([^\]]*)\]\(([^)]*)\)',lambda m:'<a href="'+m[2].replace('../','https://github.com/jcveraart/Wealth-dashboard-test/blob/main/').replace('SCREENSHOTS.md','#screenshots').replace('INSTALLATION.md','#installation').replace('CONNECTIONS.md','#connections')+'">'+m[1]+'</a>',text)
        text=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text);text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
        if line.startswith('# '):out.append(f'<h1 id="{name.lower()}">'+text[2:]+'</h1>')
        elif line.startswith('## '):out.append('<h2>'+text[3:]+'</h2>')
        elif line.startswith('### '):out.append('<h3>'+text[4:]+'</h3>')
        elif line:out.append('<p>'+text+'</p>')
    parts.append('\n'.join(table_markup(out)))
page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Wealth — installation and screenshots</title><style>body{max-width:1000px;margin:32px auto;padding:0 22px;font:16px/1.75 system-ui;color:#222;background:#fafaf8}h1{margin-top:64px;font-size:30px}h2{margin-top:36px}a{color:#26364a}code{background:#eeeee9;border-radius:5px;padding:2px 5px}pre{white-space:pre-wrap;padding:18px;background:#eeeee9;border-radius:12px}pre code{padding:0}img{display:block;max-width:100%;height:auto;border-radius:12px;border:1px solid #ddd;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd;vertical-align:top}.table-scroll{overflow:auto}li{margin:7px 0}nav{display:flex;gap:20px;flex-wrap:wrap;position:sticky;top:0;background:#fafaf8;padding:12px 0;border-bottom:1px solid #ddd}</style><nav><a href="#installation">Installation</a><a href="#connections">Connections</a><a href="#screenshots">Screenshots</a><a href="/">Dashboard</a></nav>'+''.join(parts)+'</html>'
(R/'web/guide.html').write_text(page,encoding='utf-8');print('Built self-contained in-app installation guide.')
