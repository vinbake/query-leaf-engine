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
  POST /api/session/finalize {session_id, tree, qa?, device?}
  GET  /api/prompt/<code>        (share codes persist in Postgres when DATABASE_URL is set)

Gate counting (counts.py; anonymous, to the day, no visitor identifier):
  POST /api/visit                  {kind: first|returned|daily, first_day, qa?}
  POST /api/prompt/<code>/tap      {type: copy|open_ai|share|share_open}
  POST /api/prompt/<code>/feedback {rating: yes|partly|no, text?}
  GET  /api/metrics[?as_of=YYYY-MM-DD]   counts only, no text
"""
import json
import os
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import counts
from query_engine import QueryEngine, Answer, Tree
from trees_config import load_trees_config
from au_context import load_au_context

SESSION_TTL = 30 * 60
SHARE_TTL = 90 * 24 * 3600
MAX_SESSIONS = 5000
# Where a shared prompt opens. Set PUBLIC_BASE_URL when the park's address changes.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://thequeryleaf.com.au").rstrip("/")
CODE_IN_PATH = re.compile(r"/api/prompt/[A-Za-z0-9]{6}")

TREES = load_trees_config()
AU = load_au_context()
SESSIONS = {}   # session_id -> {"engine": QueryEngine, "touched": float}
SHARES = {}     # in-memory fallback only (used when DATABASE_URL is unset or the DB errors)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
try:
    import psycopg
except ImportError:
    psycopg = None
USE_DB = bool(DATABASE_URL and psycopg)


def _db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def _db_init():
    """Create the share_codes table. Prompt text only, no visitor identifiers."""
    if not USE_DB:
        return
    try:
        with _db() as c:
            c.execute("CREATE TABLE IF NOT EXISTS share_codes ("
                      "code TEXT PRIMARY KEY, payload JSONB NOT NULL, expires_at TIMESTAMPTZ NOT NULL)")
    except Exception as e:
        print("ERROR share store init", type(e).__name__, flush=True)


def share_exists(code):
    if USE_DB:
        try:
            with _db() as c:
                return c.execute("SELECT 1 FROM share_codes WHERE code=%s", (code,)).fetchone() is not None
        except Exception as e:
            print("ERROR share store read", type(e).__name__, flush=True)
    return code in SHARES


def share_put(code, payload):
    """Returns True if stored durably."""
    if USE_DB:
        try:
            with _db() as c:
                c.execute("INSERT INTO share_codes (code, payload, expires_at) "
                          "VALUES (%s, %s::jsonb, now() + make_interval(secs => %s))",
                          (code, json.dumps(payload), SHARE_TTL))
            return True
        except Exception as e:
            print("ERROR share store write", type(e).__name__, flush=True)
    SHARES[code] = {"prompt": payload, "expires": time.time() + SHARE_TTL}
    return False


def share_get(code):
    if USE_DB:
        try:
            with _db() as c:
                row = c.execute("SELECT payload FROM share_codes WHERE code=%s AND expires_at > now()",
                                (code,)).fetchone()
                if row:
                    return row[0]
        except Exception as e:
            print("ERROR share store read", type(e).__name__, flush=True)
    hit = SHARES.get(code)
    return hit["prompt"] if hit and hit["expires"] >= time.time() else None


def share_sweep():
    if USE_DB:
        try:
            with _db() as c:
                c.execute("DELETE FROM share_codes WHERE expires_at < now()")
        except Exception as e:
            print("ERROR share store sweep", type(e).__name__, flush=True)

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
    share_sweep()


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
        # A crisis route never becomes a prompt and is never counted.
        return 200, {"ok": True, "status": "CRISIS_ROUTE", "crisis": CRISIS}
    done = s.setdefault("final", {})
    if tree_name in done:
        # Asking twice (a page reload) returns the same prompt and code, counted once.
        return 200, done[tree_name]
    out = eng.finalize_prompt(tree)
    payload = {"tree": tree_name, "pinhole": _pinhole_dict(out.pinhole),
               "prompt_text": out.prompt_text, "feedback_options": out.feedback_options}
    while share_exists(out.share_code):       # avoid collisions
        out.share_code = eng._generate_share_code()
    durable = share_put(out.share_code, payload)
    path = " > ".join(a.node_id for a in eng.answer_history if a.tree == tree)
    counts.record_interaction(out.share_code, tree_name, path, out.pinhole.root_cause,
                              device=str(body.get("device", "")), qa=bool(body.get("qa")))
    result = {"ok": True, "share_code": out.share_code, "durable": durable,
              "share_url": f"{PUBLIC_BASE_URL}/prompt/{out.share_code}",
              "cache_ttl_days": 90, **payload}
    done[tree_name] = result
    return 200, result


def visit(body):
    ok, reason = counts.record_visit(str(body.get("kind", "")), body.get("first_day"), bool(body.get("qa")))
    return (200, {"ok": True}) if ok else (200, {"ok": False, "reason": reason})


def tap(code, body):
    ok, reason = counts.record_tap(code.upper(), str(body.get("type", "")))
    if ok:
        return 200, {"ok": True}
    return (404 if reason == "unknown code" else 400), {"ok": False, "error": reason}


def feedback(code, body):
    ok, reason = counts.record_feedback(code.upper(), body.get("rating"), body.get("text"))
    if ok:
        return 200, {"ok": True}
    return (404 if reason == "unknown code" else 400), {"ok": False, "error": reason}


def selftest():
    """Run the staging-guide checks through the same code paths as live traffic.
    Sessions created here are deleted afterwards; nothing visitor-related is stored."""
    results = []
    made = []
    codes = []

    def run(tree, steps):
        _, r = start({"tree": tree})
        sid = r["session_id"]
        made.append(sid)
        last = None
        for t, node, text in steps:
            _, last = answer({"session_id": sid, "tree": t, "node_id": node, "answer_text": text})
        return sid, last

    def check(name, ok, detail=""):
        results.append({"test": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    try:
        # 1. OAK-1 single-tree narrowing
        sid, r = run("oak", [("oak", "Q1", "Income too low"),
                             ("oak", "Q2.Income", "Irregular/gig work")])
        ph = r.get("pinhole", {})
        check("1 OAK-1 narrowing",
              r.get("status") == "PINHOLE" and "Income irregularity" in ph.get("root_cause", "")
              and ph.get("confidence", 0) >= 0.85, ph.get("root_cause", ""))

        # 4. share code + 5. AU context (on the Oak session above)
        before = counts.metrics()
        _, f = finalize({"session_id": sid, "tree": "oak", "qa": True, "device": "desktop"})
        code = f.get("share_code", "")
        got = share_get(code) or {}
        check("4 Share code", bool(re.fullmatch(r"[A-Z0-9]{6}", code)) and bool(got),
              f"code format ok, retrievable, ttl {f.get('cache_ttl_days')} days, "
              f"store={'postgres' if USE_DB and f.get('durable') else 'MEMORY (not durable)'}")
        text = f.get("prompt_text", "")
        need = ["Centrelink", "13 23 17", "18,200", "Fair Work"]
        miss = [k for k in need if k not in text]
        check("5 AU context (Oak)", not miss, "missing: " + ", ".join(miss) if miss else "all present")

        # 2. RECONCILE-1 cross-tree
        sid2, r = run("gum", [("gum", "Q1", "We're fighting"), ("gum", "Q2.Fighting", "Parenting"),
                              ("acacia", "Q1", "Exhausted but wired"),
                              ("acacia", "Q2.Wired", "Gradually"), ("acacia", "Q3", "Rest")])
        trees = sorted(r.get("trees", []))
        check("2 RECONCILE-1 cross-tree", r.get("status") == "RECONCILE" and trees == ["acacia", "gum"],
              r.get("root_cause", "") or r.get("status", ""))

        # 3. ACACIA-2 crisis
        _, r = run("acacia", [("acacia", "Q1", "Everything feels too much"),
                              ("acacia", "Q4", "I'm not sure")])
        check("3 ACACIA-2 crisis route",
              r.get("status") == "CRISIS_ROUTE" and r.get("crisis", {}).get("lifeline") == "13 11 14"
              and r.get("crisis", {}).get("beyond_blue") == "1300 22 4636",
              "Lifeline 13 11 14 + Beyond Blue 1300 22 4636 returned, no prompt assembled")

        # 6. Wattle TGA guardrail present in prompt
        sidw, r = run("wattle", [("wattle", "Q1", "Energy/tiredness"), ("wattle", "Q2.Energy", "Recently"),
                                 ("wattle", "Q2.Energy.Recent", "Stress increased")])
        _, fw = finalize({"session_id": sidw, "tree": "wattle", "qa": True})
        codes.append(fw.get("share_code", ""))
        check("6 Wattle TGA guardrail", "people explore" in fw.get("prompt_text", ""),
              "guardrail wording present in Wattle prompt")

        # 7. Same-input stability: re-running OAK-1 gives the same pinhole
        _, r2 = run("oak", [("oak", "Q1", "Income too low"), ("oak", "Q2.Income", "Irregular/gig work")])
        check("7 Repeatable result", r2.get("pinhole", {}).get("root_cause") == ph.get("root_cause"), "")

        # 8-12. Gate counting. Every check reads the stored record back, not the reply.
        codes.append(code)
        row = counts.get_interaction(code) or {}
        check("8 Interaction recorded", row.get("tree") == "oak" and row.get("path") == "Q1 > Q2.Income"
              and row.get("qa") is True and row.get("copied") is False and row.get("fb_rating") is None
              and row.get("device") == "desktop",
              f"path '{row.get('path')}', store={counts.metrics().get('store')}")

        _, f2 = finalize({"session_id": sid, "tree": "oak", "qa": True})
        check("9 Finalize twice, counted once", f2.get("share_code") == code, "same code returned on a repeat")

        tap(code, {"type": "copy"})
        tap(code, {"type": "share_open"})
        feedback(code, {"rating": "partly", "text": "  selftest:   what was\nmissing  "})
        feedback(code, {"rating": "partly"})          # a bare tap must keep the text
        row = counts.get_interaction(code) or {}
        check("10 Tap and feedback stored", row.get("copied") is True and row.get("opened_ai") is False
              and row.get("share_opens") == 1 and row.get("fb_rating") == "partly"
              and row.get("fb_text") == "selftest: what was missing",
              f"copied={row.get('copied')}, rating={row.get('fb_rating')}, text kept={bool(row.get('fb_text'))}")
        feedback(code, {"rating": "yes"})
        row = counts.get_interaction(code) or {}
        bad_tap, _ = tap("ZZZZZ0", {"type": "copy"})
        check("11 Answer can change; unknown code refused", row.get("fb_rating") == "yes"
              and row.get("fb_text") is None and bad_tap == 404, "")

        visit({"kind": "first", "qa": True})
        _, same_day = visit({"kind": "returned", "first_day": counts.today().isoformat(), "qa": True})
        after = counts.metrics()
        unchanged = all(before.get(k) == after.get(k) for k in ("g1", "g2", "g3", "visits", "totals"))
        check("12 Test rows left out of the gates", unchanged
              and after["qa"]["interactions"] >= before["qa"]["interactions"] + 2
              and after["qa"]["visits"] == before["qa"]["visits"] + 1 and same_day.get("ok") is False,
              f"gate numbers unchanged={unchanged}; a same-day 'returned' is refused")
    except Exception as e:
        check("selftest runner", False, type(e).__name__)
    finally:
        for sid in made:
            SESSIONS.pop(sid, None)
        for c in codes:
            if c:
                counts.delete_interaction(c)
    passed = sum(1 for x in results if x["status"] == "PASS")
    return {"ok": passed == len(results), "passed": passed, "total": len(results), "results": results}


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

    def log_message(self, fmt, *args):   # never log bodies (visitor answers) or prompt codes
        print("%s %s" % (self.command, CODE_IN_PATH.sub("/api/prompt/<code>", self.path.split("?")[0])), flush=True)

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
                                    "version": "1.1-counting"})
        if path == "/api/selftest":
            return self._send(200, selftest())
        if path == "/api/metrics":
            as_of = parse_qs(urlsplit(self.path).query).get("as_of", [None])[0]
            return self._send(200, counts.metrics(as_of))
        if path == "/api/entry":
            return self._send(200, {"ok": True, "entry": {
                t: {"statement": TREES[t].get("entry_statement", ""),
                    "question": TREES[t].get("Q1", {}).get("question", "")} for t in TREES}})
        m = re.fullmatch(r"/api/prompt/([A-Za-z0-9]{6})", path)
        if m:
            _sweep()
            hit = share_get(m.group(1).upper())
            if not hit:
                return self._send(404, {"ok": False, "error": "code not found or expired"})
            return self._send(200, {"ok": True, **hit})
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
                  "/api/session/finalize": finalize, "/api/visit": visit}
        fn = routes.get(path)
        m = re.fullmatch(r"/api/prompt/([A-Za-z0-9]{6})/(tap|feedback)", path)
        if m:
            which = tap if m.group(2) == "tap" else feedback
            fn = lambda b, _code=m.group(1): which(_code, b)
        if not fn:
            return self._send(404, {"ok": False, "error": "not found"})
        if not isinstance(body, dict):
            return self._send(400, {"ok": False, "error": "invalid JSON"})
        try:
            code, obj = fn(body)
        except Exception as e:
            print("ERROR", type(e).__name__, flush=True)
            code, obj = 500, {"ok": False, "error": "internal error"}
        self._send(code, obj)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    _db_init()
    counts.init()
    print(f"Share store: {'postgres' if USE_DB else 'memory'}; counting store: {'postgres' if counts.USE_DB else 'memory'}", flush=True)
    print(f"Engine initialized. Trees: {list(TREES)}. Listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
