#!/usr/bin/env python3
"""Phase 2.1 AI endpoint tests: Daily Decision + AI history.

Builds the C++ server (make cpp_server), then checks the
POST /api/ai/daily-decision endpoint and the /api/ai/history
API against a LOCAL mock Gemini server — no real Gemini API is
ever called, and no real API key is used anywhere. The only key
string in this file is the fake value "test-key".

What is covered (txt mode, C++ server):
  - Daily Decision: 401 without login; 400 on missing / empty /
    over-long input and bad options; 200 with the mock reply and
    a history_id; history afterwards contains the entry.
  - History storage: prompt/response with |, backslash and quotes
    round-trip through ai_history.txt (escaped on disk); a
    multi-line mock reply round-trips through history.
  - Isolation: user B cannot see or delete user A's history;
    A can delete their own entry; ?limit= clamps the list.
  - Failure mapping: mock 401 -> 503, mock 500 -> 502, mock
    invalid JSON -> 502, mock slow + short timeout -> 504, and
    no failed call saves history.
  - No-key server: endpoint -> 503 AI unavailable (401 without
    login still comes first).
  - Python server: /api/ai/* returns 501 (401 without login).

Usage:
    python3 tests/ai_endpoints_test.py

Exit code 0 = all checks passed, 1 = at least one check failed.
"""
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

PASS = 0
FAIL = 0
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE_KEY = "test-key"
MOCK_REPLY = "Mocked AI reply."


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------- mock Gemini
class MockGemini(http.server.BaseHTTPRequestHandler):
    # behaviour is chosen by the path prefix after the host:
    #   /v1beta/...   -> 200 canned generateContent JSON
    #   /multiline/.. -> 200 with a multi-line reply text
    #   /badjson/...  -> 200 with a non-JSON body
    #   /fail500/...  -> HTTP 500
    #   /authfail/... -> HTTP 401
    #   /slow/...     -> sleep 3s, then 200 canned JSON
    requests = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        MockGemini.requests.append({
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body.decode("utf-8", "replace"),
        })
        canned = json.dumps({"candidates": [{"content": {"parts": [
            {"text": MOCK_REPLY}]}, "finishReason": "STOP"}]}).encode()
        multi = json.dumps({"candidates": [{"content": {"parts": [
            {"text": "Line one.\nLine two."}]}, "finishReason": "STOP"}]}).encode()
        try:
            if self.path.startswith("/slow/"):
                time.sleep(3)
                self._send(200, canned)
            elif self.path.startswith("/badjson/"):
                self._send(200, b"this is not json")
            elif self.path.startswith("/fail500/"):
                self._send(500, b'{"error":{"message":"boom"}}')
            elif self.path.startswith("/authfail/"):
                self._send(401, b'{"error":{"message":"bad key"}}')
            elif self.path.startswith("/multiline/"):
                self._send(200, multi)
            elif self.path.startswith("/v1beta/"):
                self._send(200, canned)
            else:
                self._send(404, b'{"error":"unknown path"}')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------- HTTP helpers
def req(port, method, path, token=None, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read() or b"{}"
            try:
                return resp.status, json.loads(raw), raw.decode("utf-8", "replace")
            except Exception:
                return resp.status, {}, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw), raw.decode("utf-8", "replace")
        except Exception:
            return e.code, {}, raw.decode("utf-8", "replace")
    except Exception as e:
        return 0, {"error": str(e)}, ""


def wait_for_server(port, timeout=30):
    for _ in range(int(timeout * 2)):
        status, _, _ = req(port, "GET", "/")
        if status != 0:
            return True
        time.sleep(0.5)
    return False


def start_cpp(port, data_dir, extra_env):
    env = dict(os.environ)
    env.pop("GEMINI_API_KEY", None)
    env.update(extra_env)
    cmd = [os.path.join(REPO, "cpp_server"), "--port", str(port),
           "--data-dir", data_dir]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)


def start_py(port, data_dir):
    env = dict(os.environ)
    env.pop("GEMINI_API_KEY", None)
    cmd = ["python3", os.path.join(REPO, "dashboard", "server.py"),
           "--port", str(port), "--data-dir", data_dir]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)


def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def register_login(port, username, password):
    status, body = req(port, "POST", "/api/register",
                       body={"username": username, "password": password})[:2]
    if status != 201:
        return None, f"register {status} {body}"
    status, body = req(port, "POST", "/api/login",
                       body={"username": username, "password": password})[:2]
    if status != 200 or "token" not in body:
        return None, f"login {status} {body}"
    return body["token"], ""


def read_history_file(data_dir):
    try:
        with open(os.path.join(data_dir, "ai_history.txt")) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def history_ids(port, token):
    status, body = req(port, "GET", "/api/ai/history", token=token)[:2]
    if status != 200:
        return None
    return [h["id"] for h in body.get("history", [])]


def main():
    tmp = tempfile.mkdtemp(prefix="pdps-ai-test-")
    mock = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockGemini)
    mock_port = mock.server_address[1]
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    print(f"mock gemini on 127.0.0.1:{mock_port}, work dir: {tmp}")
    procs = []
    try:
        # 0. Build the server.
        res = subprocess.run(["make", "cpp_server"], cwd=REPO,
                             capture_output=True, text=True)
        check("make cpp_server", res.returncode == 0,
              (res.stdout + res.stderr)[-500:])
        if res.returncode != 0:
            print(f"\nai_endpoints_test: {PASS} passed, {FAIL} failed")
            return 1

        # 1. Main server with key (mock /v1beta).
        data1 = os.path.join(tmp, "data1")
        os.makedirs(data1)
        mock_base = f"http://127.0.0.1:{mock_port}/v1beta"
        p1 = start_cpp(free_port(), data1, {
            "GEMINI_API_KEY": FAKE_KEY, "GEMINI_API_BASE_URL": mock_base})
        procs.append(p1)
        port = None
        # recover the port from the proc args
        port = int(p1.args[p1.args.index("--port") + 1])
        check("server with key starts", wait_for_server(port))

        # 1a. Auth first: 401 without login.
        status, _ = req(port, "POST", "/api/ai/daily-decision",
                        body={"input": "hello"})[:2]
        check("daily-decision without login 401", status == 401, str(status))
        status, _ = req(port, "GET", "/api/ai/history")[:2]
        check("history without login 401", status == 401, str(status))

        token_a, err = register_login(port, "alice", "AlicePass1")
        check("register+login alice", token_a is not None, err)
        token_b, err = register_login(port, "bob", "BobPass123")
        check("register+login bob", token_b is not None, err)

        # 1b. Validation: 400s, and none of them may call Gemini.
        before = len(MockGemini.requests)
        for name, body in [
                ("missing input", {}),
                ("empty input", {"input": "   "}),
                ("over-long input", {"input": "x" * 4001}),
                ("too many options", {"input": "pick one",
                                      "options": [f"o{i}" for i in range(11)]}),
                ("option too long", {"input": "pick one",
                                     "options": ["y" * 501]}),
                ("options not array", {"input": "pick one",
                                       "options": "nope"}),
                ("empty option", {"input": "pick one", "options": [""]})]:
            status, body = req(port, "POST", "/api/ai/daily-decision",
                               token=token_a, body=body)[:2]
            check(f"daily-decision 400 {name}",
                  status == 400 and body.get("error") == "invalid input",
                  f"{status} {body}")
        check("invalid inputs did not call Gemini",
              len(MockGemini.requests) == before,
              f"{len(MockGemini.requests)} vs {before}")

        # 1c. Success with options: reply + history entry.
        status, body, raw = req(port, "POST", "/api/ai/daily-decision",
                                token=token_a,
                                body={"input": "Should I study math or physics tonight?",
                                      "options": ["math", "physics"]})
        check("daily-decision 200", status == 200, f"{status} {body}")
        check("reply equals mock text",
              body.get("reply") == MOCK_REPLY, str(body))
        check("history_id is 1", body.get("history_id") == 1, str(body))
        check("response has no key", FAKE_KEY not in raw, raw[:200])
        status, body = req(port, "GET", "/api/ai/history", token=token_a)[:2]
        check("history 200", status == 200, str(body))
        hist = body.get("history", [])
        check("history has 1 entry", len(hist) == 1, str(hist))
        if hist:
            check("history feature daily-decision",
                  hist[0].get("feature") == "daily-decision", str(hist[0]))
            check("history prompt holds input",
                  "Should I study math or physics tonight?" in hist[0].get("prompt", ""),
                  str(hist[0]))
            check("history response is mock text",
                  hist[0].get("response") == MOCK_REPLY, str(hist[0]))
            check("history created_at present",
                  bool(hist[0].get("created_at")), str(hist[0]))

        # 1d. Special characters round-trip through ai_history.txt.
        tricky = 'Decide | now \\ later "quoted"'
        status, body = req(port, "POST", "/api/ai/daily-decision",
                           token=token_a, body={"input": tricky})[:2]
        check("daily-decision with | \\ \" 200", status == 200, f"{status} {body}")
        check("tricky history_id is 2", body.get("history_id") == 2, str(body))
        status, body = req(port, "GET", "/api/ai/history", token=token_a)[:2]
        hist = body.get("history", [])
        by_id = {h["id"]: h for h in hist}
        check("tricky prompt round-trips exactly",
              by_id.get(2, {}).get("prompt") == tricky,
              str(by_id.get(2)))
        raw_lines = read_history_file(data1)
        check("ai_history.txt has 2 lines",
              len([l for l in raw_lines.splitlines() if l.strip()]) == 2,
              raw_lines[:300])
        check("pipe is escaped on disk", "\\|" in raw_lines, raw_lines[:300])
        check("backslash is escaped on disk", "\\\\" in raw_lines, raw_lines[:300])

        # 1e. ?limit= clamps.
        status, body = req(port, "GET", "/api/ai/history?limit=1",
                           token=token_a)[:2]
        check("history ?limit=1 returns at most 1",
              status == 200 and len(body.get("history", [])) == 1, str(body))
        status, body = req(port, "GET", "/api/ai/history?limit=500",
                           token=token_a)[:2]
        check("history ?limit=500 clamps to stored rows",
              status == 200 and len(body.get("history", [])) == 2, str(body))

        # 1f. Isolation: bob sees nothing of alice's, cannot delete it.
        status, body = req(port, "GET", "/api/ai/history", token=token_b)[:2]
        check("bob history is empty", status == 200 and body.get("history") == [],
              str(body))
        status, body = req(port, "DELETE", "/api/ai/history/1",
                           token=token_b)[:2]
        check("bob DELETE alice entry 404", status == 404, f"{status} {body}")
        check("alice entry 1 still exists",
              1 in (history_ids(port, token_a) or []))
        # bob creates his own entry, then alice cannot see it.
        status, body = req(port, "POST", "/api/ai/daily-decision",
                           token=token_b, body={"input": "bob decision"})[:2]
        check("bob daily-decision 200", status == 200, f"{status} {body}")
        check("bob history_id is 3", body.get("history_id") == 3, str(body))
        status, body = req(port, "GET", "/api/ai/history", token=token_a)[:2]
        check("alice does not see bob entry",
              [h["id"] for h in body.get("history", [])] == [2, 1], str(body))
        # alice deletes her own entry 1.
        status, body = req(port, "DELETE", "/api/ai/history/1",
                           token=token_a)[:2]
        check("alice DELETE own entry 200",
              status == 200 and body.get("deleted") is True, f"{status} {body}")
        check("alice entry 1 gone",
              1 not in (history_ids(port, token_a) or []))
        status, _ = req(port, "DELETE", "/api/ai/history/1",
                        token=token_a)[:2]
        check("DELETE again 404", status == 404, str(status))
        status, _ = req(port, "DELETE", "/api/ai/history/abc",
                        token=token_a)[:2]
        check("DELETE non-numeric id 404", status == 404, str(status))

        # 1g. Prompt sent to Gemini holds the fixed instruction + input.
        sent = [r for r in MockGemini.requests
                if "/v1beta/" in r["path"]]
        check("mock saw gemini calls", len(sent) >= 3, str(len(sent)))
        check("instruction in sent prompt",
              any("decision assistant" in r["body"] for r in sent))
        check("user input in sent prompt",
              any("Should I study math" in r["body"] for r in sent))
        check("key in header, never in URL",
              all(FAKE_KEY not in r["path"] for r in sent))
        stop_server(p1)
        procs.remove(p1)

        # 2. Multi-line mock reply round-trips through history.
        data2 = os.path.join(tmp, "data2")
        os.makedirs(data2)
        p2 = start_cpp(free_port(), data2, {
            "GEMINI_API_KEY": FAKE_KEY,
            "GEMINI_API_BASE_URL": f"http://127.0.0.1:{mock_port}/multiline"})
        procs.append(p2)
        port2 = int(p2.args[p2.args.index("--port") + 1])
        check("multiline server starts", wait_for_server(port2))
        token_c, err = register_login(port2, "carol", "CarolPass1")
        check("register+login carol", token_c is not None, err)
        status, body = req(port2, "POST", "/api/ai/daily-decision",
                           token=token_c, body={"input": "pick"})[:2]
        check("multiline daily-decision 200", status == 200, f"{status} {body}")
        check("multiline reply has newline",
              body.get("reply") == "Line one.\nLine two.", str(body))
        status, body = req(port2, "GET", "/api/ai/history", token=token_c)[:2]
        hist = body.get("history", [])
        check("multiline reply in history",
              len(hist) == 1 and hist[0].get("response") == "Line one.\nLine two.",
              str(hist))
        raw2 = read_history_file(data2)
        check("newline escaped as \\n on disk", "\\n" in raw2, raw2[:300])
        check("file is still one line per entry",
              len([l for l in raw2.splitlines() if l.strip()]) == 1, raw2[:300])
        stop_server(p2)
        procs.remove(p2)

        # 3. Failure mapping (one server per mock mode).
        cases = [
            ("authfail", 503, "AI configuration error", "mock 401 -> 503"),
            ("fail500", 502, "AI request failed", "mock 500 -> 502"),
            ("badjson", 502, "AI request failed", "mock badjson -> 502"),
        ]
        for mode, want_status, want_err, label in cases:
            data = os.path.join(tmp, f"data-{mode}")
            os.makedirs(data)
            p = start_cpp(free_port(), data, {
                "GEMINI_API_KEY": FAKE_KEY,
                "GEMINI_API_BASE_URL": f"http://127.0.0.1:{mock_port}/{mode}"})
            procs.append(p)
            pt = int(p.args[p.args.index("--port") + 1])
            check(f"{label} server starts", wait_for_server(pt))
            tok, err = register_login(pt, "dave", "DavePass12")
            check(f"{label} login", tok is not None, err)
            status, body = req(pt, "POST", "/api/ai/daily-decision",
                               token=tok, body={"input": "will this fail?"})[:2]
            check(label, status == want_status and body.get("error") == want_err,
                  f"{status} {body}")
            check(f"{label} saves no history",
                  history_ids(pt, tok) == [], str(history_ids(pt, tok)))
            stop_server(p)
            procs.remove(p)

        # 3b. Slow mock + 1s timeout -> 504.
        data = os.path.join(tmp, "data-slow")
        os.makedirs(data)
        p = start_cpp(free_port(), data, {
            "GEMINI_API_KEY": FAKE_KEY,
            "GEMINI_API_BASE_URL": f"http://127.0.0.1:{mock_port}/slow",
            "GEMINI_TIMEOUT_SECS": "1"})
        procs.append(p)
        pt = int(p.args[p.args.index("--port") + 1])
        check("slow server starts", wait_for_server(pt))
        tok, err = register_login(pt, "erin", "ErinPass12")
        check("slow login", tok is not None, err)
        status, body = req(pt, "POST", "/api/ai/daily-decision",
                           token=tok, body={"input": "too slow?"})[:2]
        check("mock slow -> 504", status == 504 and body.get("error") == "AI request timed out",
              f"{status} {body}")
        check("slow call saves no history", history_ids(pt, tok) == [])
        stop_server(p)
        procs.remove(p)

        # 4. No-key server: 503 with login, 401 without.
        data3 = os.path.join(tmp, "data3")
        os.makedirs(data3)
        p3 = start_cpp(free_port(), data3, {})
        procs.append(p3)
        port3 = int(p3.args[p3.args.index("--port") + 1])
        check("no-key server starts", wait_for_server(port3))
        status, _ = req(port3, "POST", "/api/ai/daily-decision",
                        body={"input": "x"})[:2]
        check("no-key without login 401", status == 401, str(status))
        tok, err = register_login(port3, "fran", "FranPass12")
        check("no-key login", tok is not None, err)
        status, body = req(port3, "POST", "/api/ai/daily-decision",
                           token=tok, body={"input": "x"})[:2]
        check("no-key endpoint 503",
              status == 503 and body.get("error") == "AI unavailable",
              f"{status} {body}")
        check("no-key saves no history", history_ids(port3, tok) == [])
        stop_server(p3)
        procs.remove(p3)

        # 5. Python server: /api/ai/* -> 501 (401 without login).
        data4 = os.path.join(tmp, "data4")
        os.makedirs(data4)
        p4 = start_py(free_port(), data4)
        procs.append(p4)
        port4 = int(p4.args[p4.args.index("--port") + 1])
        check("python server starts", wait_for_server(port4))
        status, _ = req(port4, "GET", "/api/ai/health")[:2]
        check("python ai health without login 401", status == 401, str(status))
        tok, err = register_login(port4, "gail", "GailPass12")
        check("python login", tok is not None, err)
        status, body = req(port4, "GET", "/api/ai/health", token=tok)[:2]
        check("python ai health 501",
              status == 501 and body.get("error") == "AI requires the C++ server",
              f"{status} {body}")
        status, body = req(port4, "POST", "/api/ai/daily-decision",
                           token=tok, body={"input": "x"})[:2]
        check("python daily-decision 501",
              status == 501 and body.get("error") == "AI requires the C++ server",
              f"{status} {body}")
        status, _ = req(port4, "GET", "/api/health")[:2]
        check("python /api/health still 200", status == 200, str(status))
        stop_server(p4)
        procs.remove(p4)
    finally:
        for p in procs:
            try:
                stop_server(p)
            except Exception:
                pass
        try:
            mock.shutdown()
            mock.server_close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nai_endpoints_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
