"""
app.py — HTTP wrapper for the Wise Man Query Engine (Track 1).

Standard library only. One QueryEngine per visitor session, held in memory.
Phase 1 rule: no accounts, no server-side personal histories. Sessions expire
after SESSION_TTL; share-code prompts expire after SHARE_TTL (90 days, per spec)
and hold prompt text only.

Endpoints
  GET  /health | /api/health
  GET  /api/entry                      entry question per tree
  POST /api/session/start    {tree}
  POST /api/session/answer   {session_id, tree, node_id, answer_text}
  POST /api/session/finalize {session_id, tree}
  GET  /api/prompt/<code>
"""
import json
import os
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from query_engine import QueryEngine, Answer, Tree
from trees_config import load_trees_config
from au_context import load_au_context

SESSION_TTL = 30 * 60
SHARE_TTL = 90 * 24 * 3600
MAX_SESSIONS = 5000

TREES = load_trees_config()
AU = load_au_context()
SESSIONS = {}   # session_id -> {"engine": QueryEngine, "touched": float}
SHARES = {}     # code -> {"prompt": dict, "expires": float}

CRISIS = {
    "lifeline": "13 11 14",
    "beyond_blue": "1300 22 4636",
    "message": "If you or someone near you is unsafe right now, call Lifeline on 13 11 14 "
               "or Beyond Blue on 1300 22 4636. In immediate danger, call 000.",
}


def _sweep():
    now = time.time()
    for sid in [s for s, v in SESSIONS.items() if now - v["touched"] > SESSION_TTL]:
        SESSIONS.pop(sid, None)
    for code in [c for c, v in SHARES.items() if v["expires"] < now]:
        SHARES.pop(code, None)


def _node_view(tree, node_id):
    node = TREES.get(tree, {}).get(node_id)
    if not node:
        return None
    return {"tree": tree, "node_id": node_id,
            "question": node.get("question", ""), "answers": node.get("answers", [])}


def _pinhole_dict(p):
    return {"tree": p.tree.value, "root_cause": p.root_cause,
            "confidence": p.confidence, "signals": p.signals}


def start(body):
    tree = str(body.get("tree", "")).lower()
    if tree not in TREES:
        return 400, {"ok": False, "error": f"unknown tree: {tree}"}
    _sweep()
    if len(SESSIONS) >= MAX_SESSIONS:
        return 503, {"ok": False, "error": "busy, try again shortly"}
    sid = secrets.token_urlsafe(12)
    SESSIONS[sid] = {"engine": QueryEngine(TREES, AU), "touched": time.time()}
    return 200, {"ok": True, "session_id": sid, "next": _node_view(tree, "Q1")}


def answer(body):
    s = SESSIONS.get(body.get("session_id"))
    if not s:
        return 404, {"ok": False, "error": "session expired or unknown"}
    tree_name = str(body.get("tree", "")).lower()
    node_id = str(body.get("node_id", "Q1"))
    text = str(body.get("answer_text", ""))
    if tree_name not in TREES:
        return 400, {"ok": False, "error": f"unknown tree: {tree_name}"}
    s["touched"] = time.time()
    eng = s["engine"]
    tree = Tree(tree_name)
    result = eng.add_answer(Answer(node_id=node_id, tree=tree, user_response=text))

    if result == "CRISIS_ROUTE":
        return 200, {"ok": True, "status": "CRISIS_ROUTE", "crisis": CRISIS}
    if result == "PINHOLE":
        return 200, {"ok": True, "status": "PINHOLE",
                     "pinhole": _pinhole_dict(eng.pinholes[tree])}
    if result == "RECONCILE":
        rec = eng.detect_reconciliation()
        trees, cause = rec if rec else ([tree], "")
        return 200, {"ok": True, "status": "RECONCILE",
                     "trees": [t.value for t in trees], "root_cause": cause,
                     "pinholes": [_pinhole_dict(p) for p in eng.pinholes.values() if p]}
    nxt = _node_view(tree_name, result) if result else None
    if nxt:
        return 200, {"ok": True, "status": "NEXT", "next": nxt}
    return 200, {"ok": True, "status": "NONE"}


def finalize(body):
    s = SESSIONS.get(body.get("session_id"))
    if not s:
        return 404, {"ok": False, "error": "session expired or unknown"}
    tree_name = str(body.get("tree", "")).lower()
    if tree_name not in TREES:
        return 400, {"ok": False, "error": f"unknown tree: {tree_name}"}
    s["touched"] = time.time()
    eng = s["engine"]
    tree = Tree(tree_name)
    p = eng.pinholes.get(tree)
    if p is None:
        return 409, {"ok": False, "error": "no pinhole reached for this tree yet"}
    if p.root_cause == "CRISIS_ROUTE":
        return 200, {"ok": True, "status": "CRISIS_ROUTE", "crisis": CRISIS}
    out = eng.finalize_prompt(tree)
    payload = {"tree": tree_name, "pinhole": _pinhole_dict(out.pinhole),
               "prompt_text": out.prompt_text, "feedback_options": out.feedback_options}
    while out.share_code in SHARES:           # avoid collisions
        out.share_code = eng._generate_share_code()
    SHARES[out.share_code] = {"prompt": payload, "expires": time.time() + SHARE_TTL}
    return 200, {"ok": True, "share_code": out.share_code,
                 "share_url": f"https://thequeryleaf.com.au/prompt/{out.share_code}",
                 "cache_ttl_days": 90, **payload}


class Handler(BaseHTTPRequestHandler):
    server_version = "WiseMan/1.0"

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):   # never log bodies (visitor answers)
        print("%s %s" % (self.command, self.path.split("?")[0]), flush=True)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/health", "/api/health"):
            return self._send(200, {"status": "operational", "trees": len(TREES),
                                    "version": "1.0-staging"})
        if path == "/api/entry":
            return self._send(200, {"ok": True, "entry": {
                t: {"statement": TREES[t].get("entry_statement", ""),
                    "question": TREES[t].get("Q1", {}).get("question", "")} for t in TREES}})
        m = re.fullmatch(r"/api/prompt/([A-Za-z0-9]{6})", path)
        if m:
            _sweep()
            hit = SHARES.get(m.group(1).upper())
            if not hit:
                return self._send(404, {"ok": False, "error": "code not found or expired"})
            return self._send(200, {"ok": True, **hit["prompt"]})
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 20000:
                return self._send(413, {"ok": False, "error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"ok": False, "error": "invalid JSON"})
        routes = {"/api/session/start": start, "/api/session/answer": answer,
                  "/api/session/finalize": finalize}
        fn = routes.get(path)
        if not fn:
            return self._send(404, {"ok": False, "error": "not found"})
        try:
            code, obj = fn(body)
        except Exception as e:
            print("ERROR", type(e).__name__, flush=True)
            code, obj = 500, {"ok": False, "error": "internal error"}
        self._send(code, obj)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"Engine initialized. Trees: {list(TREES)}. Listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
