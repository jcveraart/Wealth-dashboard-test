"""
A model on this computer through Ollama (ollama.com), for the small, frequent jobs: which country a payment was in,
the wording of the daily briefing, grouping investments, picking news, and categorising payments. It costs nothing
and nothing leaves the computer. When Ollama isn't running, or answers badly, the job goes to Claude as before.
"""
import json
import time
import urllib.request

URL = "http://127.0.0.1:11434"
# good small models for this work, best first; any installed model works.
# These jobs are short and frequent, so a 3b that answers in seconds beats an 8b that takes a minute
# on a computer without a working GPU. The bigger ones are still preferred when they are installed.
PREFERRED = ("qwen2.5:7b", "qwen3:8b", "llama3.1:8b", "gemma2:9b", "mistral:7b", "qwen2.5:14b", "gemma3:12b", "phi4",
             "qwen2.5:3b", "llama3.2:3b", "gemma2:2b")
KINDS = {"places", "briefing", "news", "classify", "categorise"}
_state = {"checked": 0, "models": []}


def models(force=False):
    """Names of the models Ollama has installed, checked at most once a minute. Empty when Ollama isn't running."""
    if force or time.time() - _state["checked"] > 60:
        try:
            with urllib.request.urlopen(URL + "/api/tags", timeout=1.5) as r:
                _state["models"] = [m["name"] for m in json.loads(r.read()).get("models", [])]
        except Exception:
            _state["models"] = []
        _state["checked"] = time.time()
    return _state["models"]


def pick(wanted=None):
    have = models()
    if not have:
        return None
    if wanted and wanted in have:
        return wanted
    for p in PREFERRED:
        if p in have:
            return p
    return have[0]


def settings():
    try:
        import extras
        prefs = extras.ui_state()["prefs"]
        return prefs.get("local_ai", "auto"), prefs.get("local_model") or None
    except Exception:
        return "auto", None


def wanted(kind):
    """The model to use for this kind of job, or None to use Claude."""
    mode, model = settings()
    if mode == "off" or kind not in KINDS:
        return None
    return pick(model)


def run(prompt, system, model, want_json=True, timeout=240):
    body = {"model": model, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0.1, "num_ctx": 16384}}
    if want_json:
        body["format"] = "json"
    req = urllib.request.Request(URL + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def status():
    mode, model = settings()
    have = models(force=True)
    return {"mode": mode, "models": have, "model": pick(model), "kinds": sorted(KINDS)}
