"""
Run SQL on the Supabase database through the Supabase management API.

Usage:  python db.py "select * from v_institutions"
        python db.py supabase-schema.sql
Needs supabase_access_token (sbp_...) and supabase_url in settings.json.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(sql):
    s = json.loads((HERE / "settings.json").read_text(encoding="utf-8"))
    ref = s["supabase_url"].split("//")[1].split(".")[0]
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        data=json.dumps({"query": sql}).encode(), method="POST",
        headers={"Authorization": "Bearer " + s["supabase_access_token"], "Content-Type": "application/json",
                 "User-Agent": "wealth-dashboard"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"[]")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Error {e.code}: {e.read().decode('utf-8', 'replace')[:800]}")


if __name__ == "__main__":
    arg = sys.argv[1]
    sql = Path(arg).read_text(encoding="utf-8-sig") if arg.endswith(".sql") and Path(arg).exists() else arg
    print(json.dumps(run(sql), indent=2, default=str))
