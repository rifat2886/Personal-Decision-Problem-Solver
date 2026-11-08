#!/usr/bin/env python3
"""Phase 1 Gemini tests: client foundation + /api/ai/health.

Builds the C++ server (make cpp_server), then checks the Gemini
client against a LOCAL mock Gemini server — no real Gemini API is
ever called, and no real API key is used anywhere. The only key
string in this file is the fake value "test-key".

What is covered:
  1. C++ harness (compiled from dashboard/gemini_client.cpp in a
     temp dir, never committed) against the mock server:
     success, invalid-JSON response, HTTP 500, HTTP 401, timeout,
     empty/oversized prompt, missing key, and "key never appears
     in an error string".
  2. The no-libcurl stub path (compiled with -DPDPS_NO_CURL):
     available()==false and generate() -> "unavailable".
  3. The running server: /api/ai/health is 401 without a login;
     with a login it reports available/configured/model and never
     leaks the key; with GEMINI_API_KEY unset it reports
     configured=false; existing routes still work with no key.
  4. The mock server records every request: the key must arrive
     in the x-goog-api-key HEADER and never in the request URL.

Usage:
    python3 tests/gemini_test.py
    python3 tests/gemini_test.py --port 8131 --port2 8132

Exit code 0 = all checks passed, 1 = at least one check failed.
"""
import argparse
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
            {"text": "Mocked AI reply."}]}, "finishReason": "STOP"}]}).encode()
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
        with urllib.request.urlopen(r, timeout=10) as resp:
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


def start_server(port, data_dir, extra_env):
    env = dict(os.environ)
    env.pop("GEMINI_API_KEY", None)
    env.update(extra_env)
    cmd = [os.path.join(REPO, "cpp_server"), "--port", str(port),
           "--data-dir", data_dir]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)
    return proc


def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


HARNESS_CPP = r'''
// Throwaway harness (written to a temp dir by gemini_test.py, never
// committed): exercises gemini::generate() against the mock server.
// Usage: harness <mock-port>
#include "gemini_client.h"
#include <cstdio>
#include <cstdlib>
#include <string>
static int fails = 0;
static void check(const char* name, bool cond, const std::string& detail = "") {
    if (cond) { std::printf("  PASS %s\n", name); }
    else { fails++; std::printf("  FAIL %s %s\n", name, detail.c_str()); }
}
int main(int argc, char** argv) {
    std::string port = argc > 1 ? argv[1] : "0";
    std::string base = "http://127.0.0.1:" + port;
    auto setBase = [&](const std::string& suffix) {
        setenv("GEMINI_API_BASE_URL", (base + suffix).c_str(), 1);
    };
    setenv("GEMINI_API_KEY", "test-key", 1);
    unsetenv("GEMINI_TIMEOUT_SECS");
    check("available() true with libcurl", gemini::available());
    check("configured() true with key", gemini::configured());
    check("model default", gemini::modelName() == "gemini-2.0-flash", gemini::modelName());
    setBase("/v1beta");
    gemini::Result r = gemini::generate("Hello, test prompt");
    check("success ok", r.ok, r.error);
    check("success text", r.text == "Mocked AI reply.", r.text);
    setBase("/badjson");
    r = gemini::generate("Hello");
    check("invalid json -> invalid_response", !r.ok && r.error == "invalid_response", r.error);
    setBase("/fail500");
    r = gemini::generate("Hello");
    check("http500 -> request_failed", !r.ok && r.error == "request_failed", r.error);
    setBase("/authfail");
    r = gemini::generate("Hello");
    check("http401 -> auth_error", !r.ok && r.error == "auth_error", r.error);
    setBase("/slow");
    setenv("GEMINI_TIMEOUT_SECS", "1", 1);
    r = gemini::generate("Hello");
    check("slow -> timeout", !r.ok && r.error == "timeout", r.error);
    unsetenv("GEMINI_TIMEOUT_SECS");
    setBase("/v1beta");
    r = gemini::generate("");
    check("empty prompt -> invalid_request", !r.ok && r.error == "invalid_request", r.error);
    r = gemini::generate(std::string(8001, 'x'));
    check("8001-char prompt -> invalid_request", !r.ok && r.error == "invalid_request", r.error);
    unsetenv("GEMINI_API_KEY");
    check("configured() false without key", !gemini::configured());
    r = gemini::generate("Hello");
    check("no key -> not_configured", !r.ok && r.error == "not_configured", r.error);
    setenv("GEMINI_API_KEY", "test-key", 1);
    setBase("/badjson");
    r = gemini::generate("Hello");
    check("error string has no key", r.error.find("test-key") == std::string::npos, r.error);
    std::printf("harness: %s\n", fails ? "FAIL" : "ALL PASS");
    return fails ? 1 : 0;
}
'''

STUB_CPP = r'''
// Throwaway stub check (temp dir only): the no-libcurl path.
#include "gemini_client.h"
#include <cstdio>
int main() {
    if (gemini::available()) { std::printf("FAIL available() true in stub\n"); return 1; }
    std::printf("  PASS available()==false\n");
    gemini::Result r = gemini::generate("hello");
    if (r.ok || r.error != "unavailable") { std::printf("FAIL generate error=%s\n", r.error.c_str()); return 1; }
    std::printf("  PASS generate()->unavailable\n");
    gemini::Result e = gemini::generate("");
    if (e.ok || e.error != "invalid_request") { std::printf("FAIL empty prompt error=%s\n", e.error.c_str()); return 1; }
    std::printf("  PASS empty prompt->invalid_request\n");
    std::printf("stub: ALL PASS\n");
    return 0;
}
'''


def curl_flags():
    cflags, libs = "", ""
    try:
        cflags = subprocess.check_output(
            ["curl-config", "--cflags"], text=True).strip()
        libs = subprocess.check_output(
            ["curl-config", "--libs"], text=True).strip()
    except Exception:
        pass
    return cflags, libs


def compile_cpp(sources, out, pre_flags, post_flags=None):
    # Libraries must come AFTER the sources that use them, or the
    # linker reports undefined references to the curl symbols.
    cmd = (["g++", "-std=c++17", "-Wall", "-Wextra",
            "-I", os.path.join(REPO, "dashboard")] + pre_flags + sources +
           (post_flags or []) + ["-o", out])
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8131)
    ap.add_argument("--port2", type=int, default=8132)
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="pdps-gemini-test-")
    mock = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockGemini)
    mock_port = mock.server_address[1]
    mock_thread = threading.Thread(target=mock.serve_forever, daemon=True)
    mock_thread.start()
    print(f"mock gemini on 127.0.0.1:{mock_port}, work dir: {tmp}")
    cflags, libs = curl_flags()
    procs = []
    try:
        # 0. Build the server.
        res = subprocess.run(["make", "cpp_server"], cwd=REPO,
                             capture_output=True, text=True)
        check("make cpp_server", res.returncode == 0,
              (res.stdout + res.stderr)[-500:])
        if res.returncode != 0:
            print(f"\ngemini_test: {PASS} passed, {FAIL} failed")
            return 1

        # 1. C++ harness against the mock server.
        harness_cpp = os.path.join(tmp, "harness.cpp")
        with open(harness_cpp, "w") as f:
            f.write(HARNESS_CPP)
        harness_bin = os.path.join(tmp, "harness")
        res = compile_cpp(
            [harness_cpp, os.path.join(REPO, "dashboard", "gemini_client.cpp")],
            harness_bin, cflags.split(), libs.split())
        check("harness compiles clean", res.returncode == 0,
              (res.stdout + res.stderr)[-500:])
        if res.returncode == 0:
            res = subprocess.run([harness_bin, str(mock_port)],
                                 capture_output=True, text=True, timeout=120)
            print(res.stdout, end="")
            check("harness all PASS", res.returncode == 0,
                  res.stdout + res.stderr)

        # 2. No-libcurl stub path (forced with -DPDPS_NO_CURL).
        stub_cpp = os.path.join(tmp, "stub_main.cpp")
        with open(stub_cpp, "w") as f:
            f.write(STUB_CPP)
        stub_bin = os.path.join(tmp, "stub_test")
        res = compile_cpp(
            [stub_cpp, os.path.join(REPO, "dashboard", "gemini_client.cpp")],
            stub_bin, ["-DPDPS_NO_CURL"])
        check("stub compiles clean (no warnings)",
              res.returncode == 0 and res.stderr.strip() == "",
              (res.stdout + res.stderr)[-500:])
        if res.returncode == 0:
            res = subprocess.run([stub_bin], capture_output=True,
                                 text=True, timeout=30)
            print(res.stdout, end="")
            check("stub all PASS", res.returncode == 0,
                  res.stdout + res.stderr)

        # 3. Mock request inspection: key in header, never in URL.
        seen = MockGemini.requests
        check("mock saw requests", len(seen) >= 1, str(len(seen)))
        key_in_header = any(
            r["headers"].get("x-goog-api-key") == FAKE_KEY for r in seen)
        check("key sent as x-goog-api-key header", key_in_header)
        check("key never in request URL",
              all(FAKE_KEY not in r["path"] for r in seen))
        check("prompt sent as request body",
              any("Hello, test prompt" in r["body"] for r in seen))

        # 4. Server with key set: /api/ai/health auth + contract.
        data1 = os.path.join(tmp, "data1")
        os.makedirs(data1)
        mock_base = f"http://127.0.0.1:{mock_port}/v1beta"
        p1 = start_server(args.port, data1, {
            "GEMINI_API_KEY": FAKE_KEY, "GEMINI_API_BASE_URL": mock_base})
        procs.append(p1)
        check("server with key starts", wait_for_server(args.port))
        status, _, _ = req(args.port, "GET", "/api/ai/health")
        check("ai health without login 401", status == 401, str(status))
        status, body = req(args.port, "POST", "/api/register",
                           body={"username": "aiuser", "password": "AiPass123"})[:2]
        check("register aiuser", status == 201, str(body))
        status, body = req(args.port, "POST", "/api/login",
                           body={"username": "aiuser", "password": "AiPass123"})[:2]
        check("login aiuser", status == 200 and "token" in body, str(body))
        token = body.get("token", "")
        status, body, raw = req(args.port, "GET", "/api/ai/health", token=token)
        check("ai health 200 with login", status == 200, str(body))
        check("ai health available=true",
              body.get("available") is True, str(body))
        check("ai health configured=true",
              body.get("configured") is True, str(body))
        check("ai health model present",
              body.get("model") == "gemini-2.0-flash", str(body))
        check("ai health response has no key", FAKE_KEY not in raw, raw[:200])
        status, _, _ = req(args.port, "GET", "/api/health")
        check("existing /api/health still 200", status == 200, str(status))
        stop_server(p1)
        procs.remove(p1)

        # 5. Server without key: configured=false, existing routes fine.
        data2 = os.path.join(tmp, "data2")
        os.makedirs(data2)
        p2 = start_server(args.port2, data2, {})
        procs.append(p2)
        check("server without key starts", wait_for_server(args.port2))
        status, body = req(args.port2, "POST", "/api/register",
                           body={"username": "nokey", "password": "NoKey1234"})[:2]
        check("register nokey", status == 201, str(body))
        status, body = req(args.port2, "POST", "/api/login",
                           body={"username": "nokey", "password": "NoKey1234"})[:2]
        check("login nokey", status == 200 and "token" in body, str(body))
        token2 = body.get("token", "")
        status, body, raw = req(args.port2, "GET", "/api/ai/health", token=token2)
        check("ai health 200 without key", status == 200, str(body))
        check("ai health configured=false without key",
              body.get("configured") is False, str(body))
        check("ai health available=true (libcurl built)",
              body.get("available") is True, str(body))
        check("ai health no-key response has no key",
              FAKE_KEY not in raw, raw[:200])
        status, _, _ = req(args.port2, "GET", "/api/health")
        check("existing /api/health 200 without key", status == 200, str(status))
        stop_server(p2)
        procs.remove(p2)
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
    print(f"\ngemini_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
