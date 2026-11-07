"""
Is sendWidget available for this token, and on which base URL?

    BOT_TOKEN=... python3 tools/probe.py

An empty sendWidget call cannot send anything (no chat_id / html), but the error
tells whether the server knows the method:
    "Not Found"                       -> method missing on this base URL
    'parameter "html" is required'    -> method available
"""
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BASES = ["https://api.telegram.org", "https://api.telegram.org/beta"]


def call(base, method):
    req = urllib.request.Request(f"{base}/bot{TOKEN}/{method}", data=b"{}", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


if not TOKEN:
    sys.exit("set BOT_TOKEN")
for base in BASES:
    me = call(base, "getMe")
    sw = call(base, "sendWidget")
    desc = str(sw.get("description", "")).replace(TOKEN, "***")
    ok = "not found" not in desc.lower()
    print(f"{base:34} getMe={'ok' if me.get('ok') else me.get('description')}  sendWidget={'AVAILABLE' if ok else 'missing'}  ({desc})")
