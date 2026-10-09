"""Independent AI choices; OpenAI uses only ChatGPT plan OAuth, never API billing."""
import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent / 'settings.json'

def settings():
    try: return json.loads(SETTINGS.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): return {}

def selected(kind='chat', override=None):
    value = override or settings().get(kind + '_provider', 'claude')
    if value not in ('claude', 'openai'): raise ValueError('Choose Claude or OpenAI.')
    return value

def key():
    import chatgpt_auth
    return chatgpt_auth.access_token()

def openai_available(kind='import'):
    import chatgpt_auth
    return selected(kind) == 'openai' and chatgpt_auth.status()['connected']

def status():
    import chatgpt_auth
    s = settings(); connection = chatgpt_auth.status()
    return {'chat_provider': selected('chat'), 'import_provider': selected('import'),
            'has_openai_plan': connection['connected'], 'chatgpt': connection,
            'openai_chat_model': s.get('openai_chat_model') or '',
            'openai_import_model': s.get('openai_import_model') or ''}

def update(s, body):
    for name in ('chat_provider', 'import_provider'):
        if name in body:
            if body[name] not in ('claude', 'openai'): raise ValueError('Choose Claude or OpenAI.')
            s[name] = body[name]
    for name in ('openai_chat_model', 'openai_import_model'):
        if name in body:
            value = str(body[name]).strip()
            if len(value) > 100 or (value and not re.fullmatch(r'[A-Za-z0-9._:-]+', value)): raise ValueError('Enter a valid model ID.')
            s[name] = value
    # The retired API key is never accepted or used by this integration.
    return s

def content(files):
    out, total = [], 0
    import ai
    for f in ai.normalize(files):
        if f['kind'] == 'text':
            out.append({'type': 'input_text', 'text': 'File ' + f['name'] + ':\n' + f['text']})
            continue
        raw = f['raw']; total += len(raw)
        encoded = base64.b64encode(raw).decode()
        if f['kind'] == 'image':
            out.append({'type': 'input_image', 'image_url': 'data:' + f['media_type'] + ';base64,' + encoded})
        else:
            out.append({'type': 'input_file', 'filename': f['name'], 'file_data': 'data:' + f['media_type'] + ';base64,' + encoded})
    if total >= 50 * 1024 * 1024: raise ValueError('Use fewer documents: OpenAI accepts less than 50 MB per request.')
    return out

def response(messages, system, kind='chat', schema=None, files=None, level='normal', web=False, require_search=False, investment_tools=False, scope="all"):
    import chatgpt_auth
    s = settings(); model = chatgpt_auth.model(s.get('openai_' + kind + '_model'))
    token = key()
    inputs = [{'role': m['role'], 'content': [{'type': 'output_text' if m['role']=='assistant' else 'input_text', 'text': str(m['content'])}]} for m in messages]
    if files: inputs[-1]['content'] = content(files) + inputs[-1]['content']
    payload = {'model': model, 'instructions': system, 'input': inputs, 'store': False, 'stream': True}
    if re.match(r'^(gpt-[56]|o[134])', model):
        payload['reasoning'] = {'effort': {'quick':'low', 'normal':'medium', 'deep':'high'}.get(level, 'medium')}
    if schema:
        payload['text'] = {'format': {'type':'json_schema', 'name':'dashboard_import', 'strict':True, 'schema':schema}}
    if web and kind == 'chat' and not schema:
        payload['tools'] = [{'type':'web_search'}]
        payload['tool_choice'] = {'type':'web_search'} if require_search else 'auto'
    if investment_tools and kind=='chat' and not schema:
        from intelligence import tools as investment
        payload.setdefault('tools',[]).extend(investment.openai_definitions(scope))
    result = run_responses(payload, token, investment_tools, scope=scope)
    if result.get('status') == 'incomplete': raise RuntimeError('OpenAI could not finish. Try fewer files or a shorter question.')
    texts = []
    for item in result.get('output', []):
        for block in item.get('content', []):
            if block.get('type') == 'refusal': raise RuntimeError('OpenAI declined this request. Try rephrasing.')
            if block.get('type') == 'output_text': texts.append(block.get('text', ''))
    answer = ''.join(texts)
    if web: answer = cited_answer(answer, result)
    if not answer: raise RuntimeError('OpenAI returned no answer.')
    import ai
    ai.track('openai_' + kind)
    return json.loads(answer) if schema else answer

def run_responses(payload, token, investment_tools=False, scope="all"):
    for _ in range(8):
        result = request_response(payload, token)
        calls=[i for i in result.get('output',[]) if i.get('type')=='function_call']
        if not calls:return result
        if not investment_tools:raise RuntimeError('Unexpected investment tool request.')
        from intelligence import tools
        payload['input'].extend(result['output'])
        for call in calls:
            try:args=json.loads(call['arguments']);value=tools.safe_call(call['name'],args,scope)
            except (ValueError,KeyError):value={'error':'Invalid tool arguments.'}
            payload['input'].append({'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(value,default=str,allow_nan=False)})
        payload['tool_choice']='auto'
    raise RuntimeError('Research exceeded the tool limit. Try a narrower question.')

def request_response(payload, token):
    req = urllib.request.Request('https://api.openai.com/v1/responses', data=json.dumps(payload).encode(),
        headers={'Authorization':'Bearer ' + token, 'Content-Type':'application/json', 'Accept':'text/event-stream'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=600) as r: result = streamed_result(r)
    except urllib.error.HTTPError as e:
        # Subscription failures never fall back to a paid API key.
        try: error = json.loads(e.read()).get('error', {})
        except Exception: error = {}
        raise RuntimeError(plan_error(error.get('code'), e.code, error, token)) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError('Could not reach OpenAI. Check your connection.') from None
    return result


def plan_error(code=None, status=None, error=None, token=None):
    if code in ('subscription_sharing_usage_limit_exceeded', 'subscription_sharing_usage_unavailable') or status == 429:
        return 'ChatGPT plan usage is unavailable or its limit was reached. Manage usage in ChatGPT Settings, or try later. API billing is disabled.'
    if status in (401, 403):
        return 'Reconnect using Continue with ChatGPT in Settings. API billing is disabled.'
    if status == 400 and error:
        message = str(error.get('message') or 'The request format was rejected.')
        if token: message = message.replace(token, '[redacted]')
        message = re.sub(r'sk-[A-Za-z0-9_-]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+','[redacted]',message)
        return 'OpenAI rejected this request: ' + message[:350]
    return 'OpenAI could not complete this ChatGPT plan request. Please retry. API billing is disabled.'

def cited_answer(answer, result):
    from urllib.parse import urlparse
    sources={}; edits={}
    for a in result.get('_web_sources', []):
        url=a.get('url','')
        if urlparse(url).scheme not in ('http','https'): continue
        title=str(a.get('title') or urlparse(url).hostname).replace('[','').replace(']','')
        sources[url] = f'[{title}]({url})'
        if ']('+url+')' in answer:
            continue  # The model already rendered this source as a clickable Markdown link.
        start,end=a.get('start_index'),a.get('end_index')
        if isinstance(start,int) and isinstance(end,int) and 0<=start<=end<=len(answer):
            segment=answer[start:end]
            location=(start,end) if '' in segment else (end,end)
            edits.setdefault(location,[]).append(sources[url])
    # Provider citation markers are not part of the dashboard Markdown format.
    if sources:
        for (start,end),links in sorted(edits.items(), reverse=True):
            answer=answer[:start]+' '+ ' · '.join(dict.fromkeys(links))+answer[end:]
        all_links=' · '.join(sources.values())
        answer=re.sub(r'cite[^]*', ' ('+all_links+')', answer)
        if not edits and not any(url in answer for url in sources):
            answer += '\n\nSources: ' + all_links
    return answer

def streamed_result(stream):
    # SSE data may span multiple lines; accept output only after response.completed.
    data = []
    parts, finished, items = {}, {}, {}
    refusals = []
    sources = {}
    def parse(lines):
        if not lines: return None
        raw = '\n'.join(lines)
        if raw == '[DONE]': return None
        event = json.loads(raw)
        kind = event.get('type')
        index = (event.get('output_index', 0), event.get('content_index', 0))
        if kind == 'response.output_text.delta':
            parts[index] = parts.get(index, '') + event.get('delta', '')
        elif kind == 'response.output_text.done':
            finished[index] = event.get('text', parts.get(index, ''))
        elif kind == 'response.output_item.done':
            items[event.get('output_index', 0)] = event.get('item', {})
        elif kind in ('response.refusal.delta', 'response.refusal.done'):
            refusals.append(event.get('refusal') or event.get('delta') or 'Request declined.')
        if kind == 'response.output_text.annotation.added':
            a=event.get('annotation',{})
            if a.get('type')=='url_citation' and a.get('url'): sources[(a['url'],a.get('start_index'),a.get('end_index'))]=a
        if kind == 'response.content_part.done':
            for a in event.get('part',{}).get('annotations',[]):
                if a.get('type')=='url_citation' and a.get('url'): sources[(a['url'],a.get('start_index'),a.get('end_index'))]=a
        if event.get('type') in ('response.failed', 'error'):
            error = event.get('response', {}).get('error') or event.get('error') or event
            raise RuntimeError(plan_error(error.get('code')))
        if event.get('type') == 'response.incomplete':
            raise RuntimeError('OpenAI could not finish. Try fewer files or a shorter question.')
        if kind == 'response.completed':
            result = event['response']
            output = result.get('output') or [items[i] for i in sorted(items)]
            # Plan streams can omit completed text from the final response envelope.
            has_text = any(b.get('type') in ('output_text','refusal') for item in output for b in item.get('content', []))
            if not has_text:
                content = [{'type':'output_text', 'text':finished.get(i, parts.get(i, ''))}
                           for i in sorted(set(parts) | set(finished))]
                if refusals: content.append({'type':'refusal', 'refusal':''.join(refusals)})
                if content: output = output + [{'type':'message', 'role':'assistant', 'content':content}]
            result['output'] = output
            for item in output:
                for block in item.get('content',[]):
                    for a in block.get('annotations',[]):
                        if a.get('type')=='url_citation' and a.get('url'): sources[(a['url'],a.get('start_index'),a.get('end_index'))]=a
            result['_web_sources'] = list(sources.values())
            return result
        return None
    for raw in stream:
        line = raw.decode('utf-8').rstrip('\r\n')
        if not line:
            result = parse(data); data = []
            if result is not None: return result
        elif line.startswith('data:'): data.append(line[5:].lstrip(' '))
    result = parse(data)
    if result is not None: return result
    raise RuntimeError('OpenAI connection ended before the answer completed. Please retry.')
