"""Opt-in local browser for the PR125 fictional memory pilot; no Guardian startup."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time

from flask import Flask, g, jsonify, request

CODE = Path(__file__).absolute().parent
COOKIE = "elysia_pilot_session"
HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Elysia local memory pilot</title><link rel="stylesheet" href="/style.css"></head><body><main>
<h1>Elysia local memory pilot</h1><p>Fictional data only. Local evidence recall; cloud providers and autonomy are disabled. Local conversation requires an explicitly configured installed model.</p>
<form id="login"><label>Session password <input id="password" type="password" autocomplete="off" required></label><button>Connect</button></form>
<section id="work" hidden><p id="state"></p><label>Fact key <input id="key" maxlength="40" placeholder="lantern"></label>
<label>Fictional fact <textarea id="text" maxlength="700" placeholder="Fictional moonberry lantern color is violet."></textarea></label>
<button data-op="teach">Save fact</button> <button data-op="correct">Correct fact</button> <button data-op="history">History</button>
<label>Question <input id="query" maxlength="800" placeholder="What color is the moonberry lantern?"></label>
<button data-op="recall">Recall</button> <label><input id="calculate" type="checkbox">Allow the labor calculator for this question</label><button data-op="chat">Ask local model</button> <button data-op="logout">Disconnect</button></section>
<pre id="result" role="status"></pre><p>Stop the server with Ctrl+C in its terminal. Restart requires a new browser session.</p></main><script src="/app.js" defer></script></body></html>'''
STYLE = 'body{font:18px system-ui;background:#101820;color:#e9f1f7;margin:2rem}main{max-width:850px;margin:auto}label{display:block;margin:1rem 0}input,textarea{display:block;box-sizing:border-box;width:100%;padding:.6rem}button{padding:.6rem;margin:.3rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{min-height:5rem}'
JS = '''"use strict";
let csrf="";
const el=id=>document.getElementById(id);
function disconnected(){csrf="";el("work").hidden=true;el("login").hidden=false;}
async function call(path,body){
 const headers={"Content-Type":"application/json"}; if(csrf)headers["X-Elysia-CSRF"]=csrf;
 const response=await fetch(path,{method:"POST",headers,body:JSON.stringify(body),credentials:"same-origin"});
 const data=await response.json(); if(response.status===401)disconnected(); if(!response.ok)throw new Error(data.error+(data.outcome_unknown?"; outcome unknown: inspect history before retry":"")); return data;
}
el("login").onsubmit=async event=>{event.preventDefault();try{
 await call("/session",{password:el("password").value});el("password").value="";
 const r=await fetch("/api/session",{credentials:"same-origin"});if(!r.ok)throw new Error("Session unavailable");
 const s=await r.json();csrf=s.csrf;el("login").hidden=true;el("work").hidden=false;
 el("state").textContent="Connected. Synthetic memory only. Configured local model: "+(s.local_model||"none")+".";el("result").textContent="Ready.";
 }catch(e){el("password").value="";el("result").textContent=e.message;}};
document.querySelectorAll("[data-op]").forEach(button=>button.onclick=async()=>{
 document.querySelectorAll("button").forEach(b=>b.disabled=true);try{
 const op=button.dataset.op;let body={};if(op==="teach"||op==="correct")body={key:el("key").value,text:el("text").value};
 if(op==="history")body={key:el("key").value};if(op==="recall")body={query:el("query").value};if(op==="chat")body={query:el("query").value,allow_calculator:el("calculate").checked};
 const data=await call(op==="logout"?"/logout":"/api/"+op,body);
 el("result").textContent=JSON.stringify(data,null,2);
 if(op==="logout"){csrf="";el("work").hidden=true;el("login").hidden=false;}
 }catch(e){el("result").textContent=e.message;}finally{document.querySelectorAll("button").forEach(b=>b.disabled=false);}});
'''


def run_worker(store: str, command: dict) -> dict:
    # Fixed executable/file/name; never a shell, arbitrary path, or inherited API env.
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP"}}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUTF8="1")
    result = subprocess.run([sys.executable, "-S", "-B", str(CODE / "elysia_browser_worker.py"), store],
        input=json.dumps(command), text=True, encoding="utf-8", capture_output=True,
        timeout=15, cwd=CODE, env=env)
    if len(result.stdout) > 65536:
        raise RuntimeError("worker response too large")
    payload = json.loads(result.stdout)
    if type(payload) is not dict or type(payload.get("ok")) is not bool:
        raise RuntimeError("invalid worker response")
    if result.returncode != 0 and payload["ok"]:
        raise RuntimeError("worker result mismatch")
    return payload


def create_app(*, password: str, port: int, store: str = "pilot", runner=run_worker, clock=time.monotonic, local_model=None):
    if not isinstance(password, str) or not 16 <= len(password) <= 256:
        raise ValueError("Use a temporary password of 16–256 characters")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Use an explicit unprivileged port")
    if not isinstance(store, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,19}", store):
        raise ValueError("invalid synthetic store name")
    from elysia_local_memory_chat import LocalOllama, ChatBoundaryError, ManualAuthorization, converse_bundle, capability_catalog
    model = LocalOllama(local_model) if local_model is not None else None
    origin = f"http://127.0.0.1:{port}"
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    del password
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=4096, TESTING=False)
    sessions, failures = {}, []
    gate = threading.Lock()
    operation_gate = threading.Lock()
    # Validate/create the isolated store before accepting requests, never on denial.
    initial = runner(store, {"operation": "inspect"})
    if (initial.get("ok") is not True or initial.get("synthetic_only") is not True
            or initial.get("providers") is not False or initial.get("autonomy") is not False
            or initial.get("legacy_core_loaded") is not False
            or initial.get("credential_manager_loaded") is not False):
        raise RuntimeError("synthetic store unavailable; preserve it for explicit recovery")

    def error(message, status):
        return jsonify(ok=False, error=message), status

    def current_session():
        token = request.cookies.get(COOKIE, "")
        with gate:
            item = sessions.get(token)
            if item and clock() < item["expires"]:
                return item
            sessions.pop(token, None)
        return None

    @app.before_request
    def boundary():
        if request.remote_addr != "127.0.0.1" or request.host != f"127.0.0.1:{port}":
            return error("invalid_local_authority", 403)
        if request.query_string:
            return error("query_parameters_refused", 400)
        if request.method not in {"GET", "POST", "HEAD"}:
            return error("method_refused", 405)
        g.pilot_session = current_session()
        if request.method == "POST":
            if request.headers.get("Origin") != origin:
                return error("invalid_origin", 403)
            if request.mimetype != "application/json":
                return error("json_required", 415)
            if request.path != "/session":
                session = g.pilot_session
                if not session:
                    return error("unauthorized", 401)
                token = request.headers.get("X-Elysia-CSRF", "")
                if not hmac.compare_digest(token.encode("utf-8"), session["csrf"].encode("ascii")):
                    return error("invalid_csrf", 403)
        if request.path.startswith("/api/") and not g.pilot_session:
            return error("unauthorized", 401)

    @app.after_request
    def headers(response):
        response.headers.update({"Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Cross-Origin-Resource-Policy": "same-origin"})
        return response

    @app.get("/")
    def index():
        return HTML, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.get("/app.js")
    def javascript():
        return JS, 200, {"Content-Type": "application/javascript; charset=utf-8"}

    @app.get("/style.css")
    def stylesheet():
        return STYLE, 200, {"Content-Type": "text/css; charset=utf-8"}

    @app.post("/session")
    def login():
        body = request.get_json(silent=True)
        if type(body) is not dict or set(body) != {"password"} or not isinstance(body["password"], str) or len(body["password"]) > 256:
            return error("invalid_request", 400)
        now = clock()
        with gate:
            failures[:] = [stamp for stamp in failures if now - stamp < 60]
            if len(failures) >= 5:
                return error("login_rate_limited", 429)
            supplied = hashlib.scrypt(body["password"].encode(), salt=salt, n=16384, r=8, p=1)
            if not hmac.compare_digest(supplied, digest):
                failures.append(now)
                return error("unauthorized", 401)
            for key in list(sessions):
                if sessions[key]["expires"] <= now:
                    del sessions[key]
            if len(sessions) >= 8:
                return error("session_capacity", 429)
            sessions.pop(request.cookies.get(COOKIE, ""), None)
            token = secrets.token_urlsafe(32)
            sessions[token] = {"csrf": secrets.token_urlsafe(32), "expires": now + 1800}
        response = jsonify(ok=True)
        response.set_cookie(COOKIE, token, httponly=True, samesite="Strict", max_age=1800, path="/")
        return response

    @app.get("/api/session")
    def session_info():
        return jsonify(ok=True, csrf=g.pilot_session["csrf"], local_model=model.model if model else None, **{k: initial[k] for k in ("synthetic_only", "providers", "autonomy", "revision_limit")})

    @app.post("/logout")
    def logout():
        with gate:
            sessions.pop(request.cookies.get(COOKIE, ""), None)
        response = jsonify(ok=True)
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="Strict")
        return response

    @app.get("/api/capabilities")
    def capabilities():
        authorization = ManualAuthorization(secrets.token_hex(16), True, True,
                                            frozenset({"memory.read", "local.chat"}))
        return jsonify(ok=True, capabilities=capability_catalog(authorization),
                       selected_model=model.model if model else None)

    @app.get("/api/models")
    def models():
        if model is None:
            return error("local_model_not_configured", 503)
        try:
            return jsonify(ok=True, models=model.installed_models(), selected=model.model)
        except ChatBoundaryError:
            return error("local_model_catalog_unavailable", 503)

    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True)
        if (type(body) is not dict or set(body) != {"query", "allow_calculator"}
                or type(body["query"]) is not str or not 1 <= len(body["query"].strip()) <= 800
                or type(body["allow_calculator"]) is not bool):
            return error("invalid_chat_request", 400)
        if model is None:
            return error("local_model_not_configured", 503)
        if not operation_gate.acquire(blocking=False):
            return error("busy_try_after_inspection", 409)
        try:
            scopes = {"local.chat", "memory.read"}
            if body["allow_calculator"]:
                scopes.add("calculator.execute")
            authorization = ManualAuthorization(secrets.token_hex(16), True, True, frozenset(scopes))
            command = {"operation": "context", "query": body["query"]}
            before = runner(store, command)
            if not before.get("ok"):
                return error("memory_context_unavailable", 409)
            result = converse_bundle(before["bundle"], body["query"], authorization, model,
                                     g.pilot_session.get("recent", ()))
            after = runner(store, command)
            if not after.get("ok") or after.get("bundle") != before["bundle"]:
                return error("memory_changed_response_discarded", 409)
            g.pilot_session["recent"] = [
                {"question": body["query"], "answer": result["answer"][:1200]}]
            return jsonify(result)
        except ChatBoundaryError as exc:
            # Only fixed boundary messages; never echo model content or credentials.
            return error(str(exc), 503)
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
            return error("local_chat_unavailable", 503)
        finally:
            operation_gate.release()

    @app.post("/api/<operation>")
    def operate(operation):
        fields = {"teach": {"key", "text"}, "correct": {"key", "text"},
                  "history": {"key"}, "recall": {"query"}}
        if operation not in fields:
            return error("operation_refused", 404)
        body = request.get_json(silent=True)
        if type(body) is not dict or set(body) != fields[operation]:
            return error("invalid_request", 400)
        if any(not isinstance(v, str) for v in body.values()):
            return error("invalid_request", 400)
        if "key" in body and not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", body["key"]):
            return error("invalid_key", 400)
        if "text" in body and (not body["text"].startswith("Fictional ") or len(body["text"]) > 700):
            return error("fictional_text_required", 400)
        if "query" in body and not 1 <= len(body["query"].strip()) <= 800:
            return error("invalid_query", 400)
        if not operation_gate.acquire(blocking=False):
            return error("busy_try_after_inspection", 409)
        try:
            try:
                result = runner(store, {"operation": operation, **body})
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                return jsonify(ok=False, error="worker_unavailable", outcome_unknown=operation in {"teach", "correct"}), 503
            if result["ok"] and operation in {"teach", "correct"}:
                with gate:
                    for session in sessions.values():
                        session.pop("recent", None)
            return jsonify(result), 200 if result["ok"] else 409
        finally:
            operation_gate.release()

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5077)
    parser.add_argument("--store", default="pilot", help="Fictional store name; never a path")
    parser.add_argument("--local-model", help="Explicit installed local Ollama model; no download or cloud fallback")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("A local terminal is required for the temporary session password")
    from elysia_runtime_owner import runtime_owner, RuntimeOwnershipError
    try:
        with runtime_owner(CODE):
            password = getpass.getpass("Choose a temporary browser password (16–256 characters): ")
            app = create_app(password=password, port=args.port, store=args.store, local_model=args.local_model)
            del password
            print(f"Open http://127.0.0.1:{args.port}/ ; stop with Ctrl+C. Fictional memory only.", flush=True)
            app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False, threaded=False)
    except RuntimeOwnershipError as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
