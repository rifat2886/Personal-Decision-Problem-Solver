#!/usr/bin/env python3
"""Google Sign-In regression test (Phase 3, safety report section 8.2).

Exercises POST /api/auth/google, /api/auth/google/link,
/api/auth/google/unlink, /api/auth/set-password and
GET /api/auth/google/config against a LOCAL mock JWKS server. No
network, no real Google, no real client ID: the ID tokens are
minted here with throwaway RSA keys (openssl CLI) and the JWKS
server serves only those keys.

Usage:
    python3 tests/google_auth_test.py [--port 8340] [--pg-port 8341]
        [--py-port 8342] [--no-client-port 8343] [--rate-port 8344]

The C++ server is tested in BOTH storage modes (txt, then
Postgres against a throwaway local database "google_auth_test"),
plus the Python fallback server (501 checks) and two extra C++
servers (no client ID; per-IP rate limit). All test data is
throwaway and deleted with the temp directories / test database.

Exit code 0 = all checks passed, 1 = at least one check failed.
"""
import argparse
import base64
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_ID = "123456789-test.apps.googleusercontent.com"
OTHER_CLIENT_ID = "999999999-other.apps.googleusercontent.com"
PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def b64url(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


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
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def wait_for_server(port, timeout=30):
    for _ in range(int(timeout * 2)):
        status, _ = req(port, "GET", "/")
        if status != 0:
            return True
        time.sleep(0.5)
    return False


def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


# ---------------------------------------------------------------- RSA keys
# Throwaway 2048-bit RSA keys, generated with the openssl CLI
# (the `cryptography` module is not installed here). The modulus
# comes from `openssl rsa -modulus`, the exponent from the text
# output; both are base64url-encoded into the JWKS.
def gen_key(tmpdir, name):
    pem = os.path.join(tmpdir, name + ".pem")
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA",
                    "-pkeyopt", "rsa_keygen_bits:2048", "-out", pem],
                   check=True, capture_output=True)
    mod = subprocess.run(["openssl", "rsa", "-in", pem, "-noout",
                          "-modulus"], check=True, capture_output=True,
                         text=True).stdout.strip()
    n_hex = mod.split("=", 1)[1]
    text = subprocess.run(["openssl", "rsa", "-in", pem, "-noout",
                           "-text"], check=True, capture_output=True,
                          text=True).stdout
    m = re.search(r"Exponent: (\d+)", text)
    e_int = int(m.group(1))
    n = b64url(bytes.fromhex(n_hex))
    e = b64url(e_int.to_bytes((e_int.bit_length() + 7) // 8, "big"))
    return pem, n, e


def jwks_doc(keys):
    # keys: list of (kid, n, e)
    return {"keys": [{"kty": "RSA", "kid": kid, "use": "sig",
                      "alg": "RS256", "n": n, "e": e}
                     for kid, n, e in keys]}


# ---------------------------------------------------------------- mock JWKS
class MockJwks(http.server.BaseHTTPRequestHandler):
    # The test replaces `jwks` to simulate key rotation; the
    # handler re-reads it on every request. `down` makes every
    # request fail (JWKS unreachable). `hits` counts GETs, so the
    # test can prove a refresh happened.
    jwks = {"keys": []}
    down = False
    hits = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        MockJwks.hits += 1
        if MockJwks.down:
            self._send(500, b'{"error":"jwks down"}')
            return
        if self.path == "/certs":
            self._send(200, json.dumps(MockJwks.jwks).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------- token mint
def mint_token(tmpdir, sign_pem, kid, claims, alg="RS256"):
    """Mint an ID token. `sign_pem` is the key that signs it (use a
    different key than the kid's to make a wrong signature)."""
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    h = b64url(json.dumps(header, separators=(",", ":")))
    p = b64url(json.dumps(claims, separators=(",", ":")))
    signing_input = f"{h}.{p}".encode()
    if alg == "none":
        sig = b""
    elif sign_pem is None:
        sig = b"fakesig"
    else:
        in_path = os.path.join(tmpdir, "signing_input.txt")
        sig_path = os.path.join(tmpdir, "sig.bin")
        with open(in_path, "wb") as f:
            f.write(signing_input)
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", sign_pem,
                        "-out", sig_path, in_path],
                       check=True, capture_output=True)
        with open(sig_path, "rb") as f:
            sig = f.read()
    return f"{h}.{p}.{b64url(sig)}"


def make_claims(sub="111111111111111111111", email="alice@example.com",
                aud=CLIENT_ID, iss="https://accounts.google.com",
                exp=None, email_verified=True, name="Alice Example"):
    now = int(time.time())
    return {"iss": iss, "aud": aud, "sub": sub, "email": email,
            "email_verified": email_verified, "name": name,
            "iat": now, "exp": exp if exp is not None else now + 3600}


def google_signin(port, token_str):
    return req(port, "POST", "/api/auth/google",
               body={"credential": token_str})


def login(port, username, password):
    return req(port, "POST", "/api/login",
               body={"username": username, "password": password})


def register(port, username, password):
    return req(port, "POST", "/api/register",
               body={"username": username, "password": password,
                     "confirm_password": password})


# ---------------------------------------------------------------- pg helpers
def pg_query(db_url, sql):
    env = dict(os.environ)
    env["PGPASSWORD"] = "testpass"
    # The URL is postgresql://postgres:testpass@127.0.0.1:5432/<db>.
    db = db_url.rsplit("/", 1)[1]
    out = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "postgres",
                          "-d", db, "-t", "-A", "-c", sql],
                         capture_output=True, text=True, env=env)
    return out.stdout.strip()


# ---------------------------------------------------------------- one suite
def run_suite(label, port, tmp, db_url, tmpdir, key1, key2):
    """The full section-8.2 flow against one C++ server instance
    (txt when db_url is None, Postgres otherwise)."""
    print(f"\n== {label} (port {port}) ==")
    env = dict(os.environ)
    env["GOOGLE_CLIENT_ID"] = CLIENT_ID
    env["GOOGLE_JWKS_URL"] = JWKS_URL
    cmd = [os.path.join(REPO, "cpp_server"), "--port", str(port),
           "--data-dir", tmp]
    if db_url:
        env["DATABASE_URL"] = db_url
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)
    try:
        if not wait_for_server(port):
            check(f"{label}: server starts", False, "no response")
            return
        key1_pem, key1_n, key1_e = key1
        key2_pem, key2_n, key2_e = key2

        # -- config ------------------------------------------------
        status, body = req(port, "GET", "/api/auth/google/config")
        check(f"{label}: config enabled", status == 200
              and body.get("enabled") is True
              and body.get("clientId") == CLIENT_ID
              and body.get("available") is True, str(body))

        # -- first user: Google sign-in creates the ADMIN ---------
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="999999999999999999999",
                                     email="zara@example.com",
                                     name="Zara Example"))
        status, body = google_signin(port, tok)
        check(f"{label}: valid token -> 200 + session",
              status == 200 and "token" in body
              and body.get("username") == "zara"
              and body.get("role") == "ADMIN", str(body))
        token_zara = body.get("token", "")
        status, body = req(port, "GET", "/api/me", token=token_zara)
        check(f"{label}: google session works (/api/me)",
              status == 200 and body.get("username") == "zara", str(body))

        # -- username derivation on collision ---------------------
        status, body = register(port, "alice", "Alice1234")
        check(f"{label}: password user alice registers",
              status == 201, str(body))
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="111111111111111111111",
                                     email="alice@example.com"))
        status, body = google_signin(port, tok)
        check(f"{label}: collision -> username alice-111111",
              status == 200 and body.get("username") == "alice-111111"
              and body.get("role") == "USER", str(body))
        token_alice = body.get("token", "")

        # -- token failures ---------------------------------------
        tok = mint_token(tmpdir, key2_pem, "key1",
                         make_claims(sub="555555555555555555555",
                                     email="mallory@example.com"))
        status, body = google_signin(port, tok)
        check(f"{label}: wrong signature -> 401", status == 401, str(body))
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="555555555555555555555",
                                     email="mallory@example.com",
                                     exp=int(time.time()) - 3600))
        status, body = google_signin(port, tok)
        check(f"{label}: expired token -> 401", status == 401, str(body))
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="555555555555555555555",
                                     email="mallory@example.com",
                                     aud=OTHER_CLIENT_ID))
        status, body = google_signin(port, tok)
        check(f"{label}: wrong audience -> 401", status == 401, str(body))
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="555555555555555555555",
                                     email="mallory@example.com",
                                     iss="https://evil.example.com"))
        status, body = google_signin(port, tok)
        check(f"{label}: wrong issuer -> 401", status == 401, str(body))
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="555555555555555555555",
                                     email="mallory@example.com",
                                     email_verified=False))
        status, body = google_signin(port, tok)
        check(f"{label}: email_verified false -> 401",
              status == 401, str(body))
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="555555555555555555555",
                                     email="mallory@example.com"),
                         alg="none")
        status, body = google_signin(port, tok)
        check(f"{label}: alg none -> 401", status == 401, str(body))
        tok = mint_token(tmpdir, None, "key1",
                         make_claims(sub="555555555555555555555",
                                     email="mallory@example.com"),
                         alg="HS256")
        status, body = google_signin(port, tok)
        check(f"{label}: alg HS256 -> 401", status == 401, str(body))

        # -- unknown kid -> JWKS refresh + verify -----------------
        hits_before = MockJwks.hits
        MockJwks.jwks = jwks_doc([("key1", key1_n, key1_e),
                                  ("key2", key2_n, key2_e)])
        tok = mint_token(tmpdir, key2_pem, "key2",
                         make_claims(sub="222222222222222222222",
                                     email="kate@example.com",
                                     name="Kate Example"))
        status, body = google_signin(port, tok)
        check(f"{label}: unknown kid refreshes JWKS and verifies",
              status == 200 and body.get("username") == "kate", str(body))
        check(f"{label}: JWKS was re-fetched for the new kid",
              MockJwks.hits > hits_before, f"hits {hits_before} -> {MockJwks.hits}")

        # -- duplicate google_sub -> same account -----------------
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="999999999999999999999",
                                     email="zara@example.com",
                                     name="Zara Example"))
        status, body = google_signin(port, tok)
        check(f"{label}: duplicate sub -> same account",
              status == 200 and body.get("username") == "zara", str(body))
        status, body = req(port, "GET", "/api/users", token=token_zara)
        users = body if isinstance(body, list) else []
        check(f"{label}: no duplicate account created",
              status == 200 and len(users) == 4, str(body)[:200])

        # -- duplicate email on a different sub -> 409 ------------
        tok = mint_token(tmpdir, key1_pem, "key1",
                         make_claims(sub="333333333333333333333",
                                     email="alice@example.com"))
        status, body = google_signin(port, tok)
        check(f"{label}: duplicate email, different sub -> 409",
              status == 409, str(body))

        # -- link / unlink / set-password -------------------------
        status, body = register(port, "bob", "Bob12345")
        check(f"{label}: password user bob registers",
              status == 201, str(body))
        status, body = login(port, "bob", "Bob12345")
        token_bob = body.get("token", "")
        check(f"{label}: bob logs in", status == 200 and token_bob, str(body))
        tok_bob = mint_token(tmpdir, key1_pem, "key1",
                             make_claims(sub="444444444444444444444",
                                         email="bob@example.com",
                                         name="Bob Example"))
        status, body = req(port, "POST", "/api/auth/google/link",
                           token=token_bob, body={"credential": tok_bob})
        check(f"{label}: link google to bob -> 200",
              status == 200 and body.get("linked") is True, str(body))
        status, body = google_signin(port, tok_bob)
        check(f"{label}: google sign-in after link is bob",
              status == 200 and body.get("username") == "bob", str(body))
        token_bob_google = body.get("token", "")
        status, body = req(port, "POST", "/api/auth/google/link",
                           token=token_bob, body={"credential": tok_bob})
        check(f"{label}: link same sub again is a no-op 200",
              status == 200 and body.get("linked") is True, str(body))
        tok_other = mint_token(tmpdir, key2_pem, "key2",
                               make_claims(sub="666666666666666666666",
                                           email="other@example.com"))
        status, body = req(port, "POST", "/api/auth/google/link",
                           token=token_bob, body={"credential": tok_other})
        check(f"{label}: link a different sub to bob -> 409",
              status == 409, str(body))
        status, body = register(port, "carol", "Carol123")
        check(f"{label}: password user carol registers",
              status == 201, str(body))
        status, body = login(port, "carol", "Carol123")
        token_carol = body.get("token", "")
        status, body = req(port, "POST", "/api/auth/google/link",
                           token=token_carol, body={"credential": tok_bob})
        check(f"{label}: link bob's sub to carol -> 409",
              status == 409, str(body))

        # Unlink bob (he has a password, so it is allowed), then
        # a Google sign-in with his sub must fail: his email is
        # still held by his account.
        status, body = req(port, "POST", "/api/auth/google/unlink",
                           token=token_bob, body={})
        check(f"{label}: unlink bob (has password) -> 200",
              status == 200 and body.get("unlinked") is True, str(body))
        status, body = google_signin(port, tok_bob)
        check(f"{label}: google sign-in after unlink -> 409 (email held)",
              status == 409, str(body))

        # Re-link bob, then set a password from the fresh Google
        # session; the new password must work for password login.
        status, body = req(port, "POST", "/api/auth/google/link",
                           token=token_bob, body={"credential": tok_bob})
        check(f"{label}: re-link bob -> 200",
              status == 200 and body.get("linked") is True, str(body))
        status, body = google_signin(port, tok_bob)
        token_bob_google = body.get("token", "")
        status, body = req(port, "POST", "/api/auth/set-password",
                           token=token_bob_google,
                           body={"password": "BobNew123",
                                 "confirm_password": "BobNew123"})
        check(f"{label}: set-password from fresh google session -> 200",
              status == 200, str(body))
        status, body = login(port, "bob", "BobNew123")
        check(f"{label}: password login works after set-password",
              status == 200 and "token" in body, str(body))

        # Set-password via a fresh token in the body (no fresh
        # Google session): log bob in with his password, then pass
        # a fresh token for his own sub.
        status, body = login(port, "bob", "BobNew123")
        token_bob_pw = body.get("token", "")
        tok_bob_fresh = mint_token(tmpdir, key1_pem, "key1",
                                   make_claims(sub="444444444444444444444",
                                               email="bob@example.com"))
        status, body = req(port, "POST", "/api/auth/set-password",
                           token=token_bob_pw,
                           body={"password": "BobNew234",
                                 "confirm_password": "BobNew234",
                                 "credential": tok_bob_fresh})
        check(f"{label}: set-password with fresh token in body -> 200",
              status == 200, str(body))
        # Same call with no fresh session and no token -> 401.
        status, body = req(port, "POST", "/api/auth/set-password",
                           token=token_bob_pw,
                           body={"password": "BobNew345",
                                 "confirm_password": "BobNew345"})
        check(f"{label}: set-password without fresh proof -> 401",
              status == 401, str(body))
        # A pure password user has no Google link -> 400.
        status, body = login(port, "carol", "Carol123")
        token_carol = body.get("token", "")
        status, body = req(port, "POST", "/api/auth/set-password",
                           token=token_carol,
                           body={"password": "CarolNew1",
                                 "confirm_password": "CarolNew1"})
        check(f"{label}: set-password with no google link -> 400",
              status == 400, str(body))

        # -- last-method guard ------------------------------------
        tok_dave = mint_token(tmpdir, key1_pem, "key1",
                              make_claims(sub="777777777777777777777",
                                          email="dave@example.com",
                                          name="Dave Example"))
        status, body = google_signin(port, tok_dave)
        check(f"{label}: google-only user dave signs in",
              status == 200 and body.get("username") == "dave", str(body))
        token_dave = body.get("token", "")
        status, body = req(port, "POST", "/api/auth/google/unlink",
                           token=token_dave, body={})
        check(f"{label}: unlink only sign-in method -> 409",
              status == 409, str(body))

        # -- Google-only user cannot log in with any password ----
        status, body = login(port, "dave", "Whatever123")
        check(f"{label}: google-only login with any password -> 401",
              status == 401, str(body))
        if db_url:
            val = pg_query(db_url,
                           "SELECT password_hash IS NULL FROM users "
                           "WHERE username = 'dave';")
            check(f"{label}: google-only password_hash is NULL in pg",
                  val == "t", f"got {val!r}")
        else:
            with open(os.path.join(tmp, "users.txt")) as f:
                lines = f.read()
            check(f"{label}: google-only stored as 'dave! ROLE' in txt",
                  "dave! USER" in lines, lines[:200])
    finally:
        stop_server(proc)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8340)
    ap.add_argument("--pg-port", type=int, default=8341)
    ap.add_argument("--py-port", type=int, default=8342)
    ap.add_argument("--no-client-port", type=int, default=8343)
    ap.add_argument("--rate-port", type=int, default=8344)
    args = ap.parse_args()
    tmpdir = tempfile.mkdtemp(prefix="pdps-google-auth-test-")
    print(f"work dir: {tmpdir}")

    # -- mock JWKS server (shared by every server below) ---------
    key1 = gen_key(tmpdir, "key1")
    key2 = gen_key(tmpdir, "key2")
    MockJwks.jwks = jwks_doc([("key1", key1[1], key1[2])])
    jwks_port = free_port()
    global JWKS_URL
    JWKS_URL = f"http://127.0.0.1:{jwks_port}/certs"
    jwks_srv = http.server.ThreadingHTTPServer(("127.0.0.1", jwks_port),
                                               MockJwks)
    threading.Thread(target=jwks_srv.serve_forever, daemon=True).start()
    print(f"mock JWKS: {JWKS_URL} (kid key1 only)")

    # -- throwaway Postgres database for the pg suite -------------
    pg_env = dict(os.environ)
    pg_env["PGPASSWORD"] = "testpass"
    db_url = None
    try:
        subprocess.run(["sudo", "-u", "postgres", "dropdb", "--if-exists",
                        "google_auth_test"],
                       capture_output=True, check=False)
        subprocess.run(["sudo", "-u", "postgres", "createdb",
                        "google_auth_test"],
                       capture_output=True, check=True)
        db_url = ("postgresql://postgres:testpass@127.0.0.1:5432/"
                  "google_auth_test")
        print("pg test database: google_auth_test")
    except Exception as e:
        print(f"WARNING: could not create pg test database ({e}); "
              "pg suite will be skipped")

    try:
        # -- txt mode --------------------------------------------
        # Reset the mock JWKS to key1-only before each suite: the
        # rotation test needs the server's cache to genuinely lack
        # key2, so the kid2 token forces a JWKS refresh.
        MockJwks.jwks = jwks_doc([("key1", key1[1], key1[2])])
        tmp_txt = tempfile.mkdtemp(prefix="pdps-google-txt-")
        run_suite("txt", args.port, tmp_txt, None, tmpdir, key1, key2)
        shutil.rmtree(tmp_txt, ignore_errors=True)

        # -- Postgres mode ---------------------------------------
        if db_url:
            MockJwks.jwks = jwks_doc([("key1", key1[1], key1[2])])
            tmp_pg = tempfile.mkdtemp(prefix="pdps-google-pg-")
            run_suite("pg", args.pg_port, tmp_pg, db_url, tmpdir, key1, key2)
            shutil.rmtree(tmp_pg, ignore_errors=True)
        else:
            check("pg suite skipped (no test database)", False,
                  "createdb failed")

        # -- Python server: Google auth -> 501 --------------------
        print(f"\n== python (port {args.py_port}) ==")
        tmp_py = tempfile.mkdtemp(prefix="pdps-google-py-")
        with open(os.path.join(tmp_py, "users.txt"), "w") as f:
            f.write("olduser OldPass123 ADMIN\n")
        cmd = ["python3", os.path.join(REPO, "dashboard", "server.py"),
               "--port", str(args.py_port), "--data-dir", tmp_py]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        try:
            if not wait_for_server(args.py_port):
                check("python: server starts", False, "no response")
            else:
                status, body = login(args.py_port, "olduser", "OldPass123")
                token_py = body.get("token", "")
                check("python: login works", status == 200 and token_py,
                      str(body))
                status, body = req(args.py_port, "GET",
                                   "/api/auth/google/config", token=token_py)
                check("python: config -> 501", status == 501, str(body))
                status, body = req(args.py_port, "POST", "/api/auth/google",
                                   token=token_py,
                                   body={"credential": "x.y.z"})
                check("python: google sign-in -> 501", status == 501, str(body))
                status, body = req(args.py_port, "POST",
                                   "/api/auth/google/link", token=token_py,
                                   body={"credential": "x.y.z"})
                check("python: link -> 501", status == 501, str(body))
                status, body = req(args.py_port, "POST",
                                   "/api/auth/google/unlink",
                                   token=token_py, body={})
                check("python: unlink -> 501", status == 501, str(body))
                status, body = req(args.py_port, "POST",
                                   "/api/auth/set-password",
                                   token=token_py,
                                   body={"password": "NewPass123",
                                         "confirm_password": "NewPass123"})
                check("python: set-password -> 501", status == 501, str(body))
                status, body = req(args.py_port, "POST", "/api/auth/google",
                                   body={"credential": "x.y.z"})
                check("python: google sign-in without token -> 401",
                      status == 401, str(status))
        finally:
            stop_server(proc)
            shutil.rmtree(tmp_py, ignore_errors=True)

        # -- C++ server without a client ID -----------------------
        print(f"\n== no-client (port {args.no_client_port}) ==")
        tmp_nc = tempfile.mkdtemp(prefix="pdps-google-nc-")
        env = dict(os.environ)
        env.pop("GOOGLE_CLIENT_ID", None)
        env["GOOGLE_JWKS_URL"] = JWKS_URL
        cmd = [os.path.join(REPO, "cpp_server"), "--port",
               str(args.no_client_port), "--data-dir", tmp_nc]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=env)
        try:
            if not wait_for_server(args.no_client_port):
                check("no-client: server starts", False, "no response")
            else:
                status, body = req(args.no_client_port, "GET",
                                   "/api/auth/google/config")
                check("no-client: config enabled=false",
                      status == 200 and body.get("enabled") is False
                      and body.get("clientId") == "", str(body))
                status, body = req(args.no_client_port, "POST",
                                   "/api/auth/google",
                                   body={"credential": "x.y.z"})
                check("no-client: google sign-in -> 503",
                      status == 503, str(body))
        finally:
            stop_server(proc)
            shutil.rmtree(tmp_nc, ignore_errors=True)

        # -- per-IP rate limit (dedicated server) -----------------
        print(f"\n== rate-limit (port {args.rate_port}) ==")
        tmp_rl = tempfile.mkdtemp(prefix="pdps-google-rl-")
        env = dict(os.environ)
        env["GOOGLE_CLIENT_ID"] = CLIENT_ID
        env["GOOGLE_JWKS_URL"] = JWKS_URL
        cmd = [os.path.join(REPO, "cpp_server"), "--port",
               str(args.rate_port), "--data-dir", tmp_rl]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=env)
        try:
            if not wait_for_server(args.rate_port):
                check("rate-limit: server starts", False, "no response")
            else:
                codes = []
                for _ in range(21):
                    status, _ = req(args.rate_port, "POST",
                                    "/api/auth/google",
                                    body={"credential": "x.y.z"})
                    codes.append(status)
                check("rate-limit: first 20 attempts are not 429",
                      all(c != 429 for c in codes[:20]), str(codes))
                check("rate-limit: 21st attempt in 60s -> 429",
                      codes[20] == 429, str(codes))
        finally:
            stop_server(proc)
            shutil.rmtree(tmp_rl, ignore_errors=True)
    finally:
        jwks_srv.shutdown()
        if db_url:
            subprocess.run(["sudo", "-u", "postgres", "dropdb",
                            "--if-exists", "google_auth_test"],
                           capture_output=True, check=False)
        shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"\ngoogle_auth_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
