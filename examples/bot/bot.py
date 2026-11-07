"""
Minimal HTML Bubbles bot (Bot API 10.4, beta). Python 3.8+, standard library only.

Commands:
    /hello    -> examples/widgets/01-hello.html
    /counter  -> examples/widgets/02-tap-counter.html
    /anim     -> examples/widgets/03-animation-paint-safe.html
    /poll     -> examples/widgets/04-poll.html  (answers widget_query, edits public_data)

Run:
    cp .env.example .env   # fill BOT_TOKEN
    ./run.sh               # or: set -a; source .env; set +a; python3 examples/bot/bot.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zlib

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
API_BASE = os.environ.get("API_BASE", "https://api.telegram.org/beta").rstrip("/")
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDGETS = os.path.join(ROOT, "widgets")
COMMANDS = {
    "/hello": "01-hello.html",
    "/counter": "02-tap-counter.html",
    "/anim": "03-animation-paint-safe.html",
    "/poll": "04-poll.html",
}

MAX_RAW, MAX_ZLIB = 32768, 4096

# poll state in memory: "chat_id:message_id" -> {"q","o","v","r","voters"}
POLLS = {}


class ApiError(Exception):
    pass


def api(method, payload=None, timeout=60):
    req = urllib.request.Request(
        f"{API_BASE}/bot{TOKEN}/{method}",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read().decode("utf-8"))
        except Exception:
            res = {"ok": False, "description": f"HTTP {e.code}"}
    if not res.get("ok"):
        raise ApiError(str(res.get("description", res)).replace(TOKEN, "***"))
    return res["result"]


def load_widget(name):
    with open(os.path.join(WIDGETS, name), "rb") as f:
        raw = f.read()
    # same check as the server (PHP gzcompress level 9 == zlib level 9)
    z = len(zlib.compress(raw, 9))
    if len(raw) > MAX_RAW or z > MAX_ZLIB:
        raise ApiError(f"{name} too large: {len(raw)} B raw / {z} B zlib (limit {MAX_RAW} / {MAX_ZLIB})")
    return raw.decode("utf-8")


def public_poll(p):
    return json.dumps({k: p[k] for k in ("q", "o", "v", "r")}, ensure_ascii=False)


def send(chat_id, cmd):
    html = load_widget(COMMANDS[cmd])
    if cmd != "/poll":
        # width/height 0 (or omitted) = auto: bubble width, content height
        return api("sendWidget", {"chat_id": chat_id, "html": html})
    poll = {"q": "Tabs or spaces?", "o": ["Tabs", "Spaces", "Whatever the linter says"], "v": [0, 0, 0], "r": 0, "voters": {}}
    msg = api("sendWidget", {
        "chat_id": chat_id,
        "html": html,
        "allow_queries": True,          # without it every request() is NOT_ALLOWED
        "public_data": public_poll(poll),
    })
    POLLS[f"{chat_id}:{msg['message_id']}"] = poll
    return msg


def on_widget_query(q):
    """Return the answer dict; it goes back to the widget as `result` (<= 1024 bytes)."""
    if not q.get("chat"):
        return {"msg": "Not supported here"}
    key = f"{q['chat']['id']}:{q['message_id']}"
    poll = POLLS.get(key)
    data = q.get("data", "")
    if not poll or not data.startswith("vote:"):
        return {"msg": "This poll has expired"}
    try:
        i = int(data[5:])
        poll["o"][i]
    except (ValueError, IndexError):
        return {"msg": "Bad option"}
    uid = str(q["from"]["id"])
    if uid in poll["voters"]:
        return {"msg": "You already voted", "state": json.loads(public_poll(poll))}
    # edit first, commit after: a failed edit must not eat the vote
    nxt = dict(poll, v=poll["v"][:], r=poll["r"] + 1)
    nxt["v"][i] += 1
    try:
        api("editMessageWidgetData", {"chat_id": q["chat"]["id"], "message_id": q["message_id"], "public_data": public_poll(nxt)})
    except ApiError as e:
        if "not modified" not in str(e):
            raise
    nxt["voters"] = dict(poll["voters"], **{uid: i})
    POLLS[key] = nxt
    return {"msg": "Vote counted", "state": json.loads(public_poll(nxt))}


def handle(u):
    if "message" in u:
        m = u["message"]
        if ALLOWED and (m.get("from") or {}).get("id") not in ALLOWED:
            return
        cmd = (m.get("text") or "").strip().split("@")[0].lower()
        if cmd in COMMANDS:
            try:
                send(m["chat"]["id"], cmd)
            except ApiError as e:
                print("send failed:", e)
                api("sendMessage", {"chat_id": m["chat"]["id"], "text": f"Widget not sent: {e}"})
    q = u.get("widget_query") or u.get("shared_widget_query")
    if q:
        try:
            answer = on_widget_query(q)
        except Exception as e:  # always answer, or the widget gets TIMEOUT
            print("query failed:", e)
            answer = {"msg": "Server error"}
        api("answerWidgetQuery", {"widget_query_id": q["id"], "data": json.dumps(answer, ensure_ascii=False)})


def main():
    if not TOKEN:
        sys.exit("BOT_TOKEN is not set (see .env.example)")
    me = api("getMe")
    print(f"@{me['username']} via {API_BASE}")
    offset = None
    while True:
        try:
            payload = {"timeout": 30, "allowed_updates": ["message", "widget_query", "shared_widget_query"]}
            if offset:
                payload["offset"] = offset
            for u in api("getUpdates", payload, timeout=40):
                offset = u["update_id"] + 1
                handle(u)
        except (urllib.error.URLError, TimeoutError, ApiError) as e:
            print("retrying:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
