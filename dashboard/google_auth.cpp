// google_auth.cpp — Google ID-token verification (see google_auth.h).
//
// The token is verified locally against Google's public keys (JWKS):
// structure -> header alg/kid -> payload claims (iss/aud/exp/
// email_verified/sub) -> JWKS fetch + cache -> RS256 signature
// with OpenSSL EVP_DigestVerify. The token is never stored and
// never logged; only sub/email/name leave this module (in Claims).
//
// This file is self-contained: it has its own minimal strict JSON
// reader (the strict helpers in cpp_server.cpp are static there)
// and its own libcurl GET (gemini_client is POST-only).

#include "google_auth.h"

#include <cctype>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <map>
#include <mutex>
#include <vector>

#if !defined(PDPS_NO_OPENSSL) && !defined(PDPS_NO_CURL) && defined(__has_include)
#if __has_include(<openssl/evp.h>) && __has_include(<openssl/params.h>) && \
    __has_include(<openssl/core_names.h>) && __has_include(<curl/curl.h>)
#define PDPS_HAVE_GOOGLE_AUTH 1
#endif
#endif

namespace google_auth {

namespace {

// Longest ID token accepted (real tokens are ~1-2 KB; anything
// larger is not a Google token).
const size_t kMaxTokenChars = 8192;
// JWKS cache lifetime: refresh at most once an hour, or sooner
// when an unknown kid arrives.
const long long kJwksCacheSecs = 3600;

}  // namespace

bool configured() {
    const char* v = std::getenv("GOOGLE_CLIENT_ID");
    return v != nullptr && v[0] != '\0';
}

bool enabled() {
    if (!configured()) return false;
    const char* v = std::getenv("GOOGLE_SIGNIN_ENABLED");
    return v == nullptr || std::string(v) != "0";
}

std::string clientId() {
    const char* v = std::getenv("GOOGLE_CLIENT_ID");
    return (v != nullptr) ? std::string(v) : std::string();
}

#ifdef PDPS_HAVE_GOOGLE_AUTH

#include <curl/curl.h>
#include <openssl/bn.h>
#include <openssl/core_names.h>
#include <openssl/evp.h>
#include <openssl/param_build.h>
#include <openssl/params.h>

namespace {

// Default JWKS endpoint (Google's public certs). Overridable by
// GOOGLE_JWKS_URL — used to point at a mock JWKS server in tests.
const char* kDefaultJwksUrl = "https://www.googleapis.com/oauth2/v3/certs";

// The JWKS URL: GOOGLE_JWKS_URL when set, else Google's certs.
std::string jwksUrl() {
    const char* v = std::getenv("GOOGLE_JWKS_URL");
    if (v != nullptr && v[0] != '\0') return std::string(v);
    return std::string(kDefaultJwksUrl);
}

// ------------------------------------------------------------ base64url
int b64Val(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '-') return 62;
    if (c == '_') return 63;
    return -1;
}

// Strict base64url decode (JWT alphabet, padding optional).
// Rejects bad characters, bad lengths, and embedded whitespace.
bool base64UrlDecode(const std::string& in, std::string& out) {
    if (in.empty() || in.size() % 4 == 1) return false;
    std::string s = in;
    while (s.size() % 4 != 0) s += '=';
    out.clear();
    for (size_t i = 0; i < s.size(); i += 4) {
        int v[4];
        int pad = 0;
        for (int j = 0; j < 4; j++) {
            char c = s[i + j];
            if (c == '=') { v[j] = 0; pad++; }
            else {
                v[j] = b64Val(c);
                if (v[j] < 0) return false;
            }
        }
        if (pad > 2) return false;
        out += static_cast<char>((v[0] << 2) | (v[1] >> 4));
        if (pad < 2) out += static_cast<char>(((v[1] & 0xF) << 4) | (v[2] >> 2));
        if (pad < 1) out += static_cast<char>(((v[2] & 0x3) << 6) | v[3]);
    }
    return true;
}

// ------------------------------------------------------------ strict JSON
size_t skipWs(const std::string& s, size_t p) {
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n' || s[p] == '\r')) p++;
    return p;
}

// End position just past a JSON string starting at p (p must be
// at the opening '"'), or npos when malformed. Backslash escapes
// are skipped, so an escaped quote never ends the string.
size_t jsonStringEnd(const std::string& s, size_t p) {
    if (p >= s.size() || s[p] != '"') return std::string::npos;
    p++;
    while (p < s.size()) {
        if (s[p] == '\\') { p += 2; continue; }
        if (s[p] == '"') return p + 1;
        if (static_cast<unsigned char>(s[p]) < 0x20) return std::string::npos;
        p++;
    }
    return std::string::npos;
}

void appendUtf8(std::string& out, unsigned cp) {
    if (cp < 0x80) {
        out += static_cast<char>(cp);
    } else if (cp < 0x800) {
        out += static_cast<char>(0xC0 | (cp >> 6));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        out += static_cast<char>(0xE0 | (cp >> 12));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
        out += static_cast<char>(0xF0 | (cp >> 18));
        out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    }
}

// Decode a JSON string literal (including its quotes). Standard
// escapes and \uXXXX (with surrogate pairs) are decoded.
bool decodeJsonString(const std::string& lit, std::string& out) {
    if (lit.size() < 2 || lit.front() != '"' || lit.back() != '"') return false;
    out.clear();
    size_t p = 1, end = lit.size() - 1;
    auto hexVal = [&](size_t q) -> int {
        char h = lit[q];
        if (h >= '0' && h <= '9') return h - '0';
        if (h >= 'a' && h <= 'f') return h - 'a' + 10;
        if (h >= 'A' && h <= 'F') return h - 'A' + 10;
        return -1;
    };
    while (p < end) {
        char c = lit[p];
        if (c == '\\') {
            if (p + 1 >= end) return false;
            char e = lit[p + 1];
            switch (e) {
                case '"': out += '"'; p += 2; break;
                case '\\': out += '\\'; p += 2; break;
                case '/': out += '/'; p += 2; break;
                case 'b': out += '\b'; p += 2; break;
                case 'f': out += '\f'; p += 2; break;
                case 'n': out += '\n'; p += 2; break;
                case 'r': out += '\r'; p += 2; break;
                case 't': out += '\t'; p += 2; break;
                case 'u': {
                    if (p + 5 >= end) return false;
                    int d0 = hexVal(p + 2), d1 = hexVal(p + 3), d2 = hexVal(p + 4), d3 = hexVal(p + 5);
                    if (d0 < 0 || d1 < 0 || d2 < 0 || d3 < 0) return false;
                    unsigned cp = static_cast<unsigned>((d0 << 12) | (d1 << 8) | (d2 << 4) | d3);
                    p += 6;
                    if (cp >= 0xD800 && cp <= 0xDBFF) {
                        if (p + 5 >= end || lit[p] != '\\' || lit[p + 1] != 'u') return false;
                        int f0 = hexVal(p + 2), f1 = hexVal(p + 3), f2 = hexVal(p + 4), f3 = hexVal(p + 5);
                        if (f0 < 0 || f1 < 0 || f2 < 0 || f3 < 0) return false;
                        unsigned lo = static_cast<unsigned>((f0 << 12) | (f1 << 8) | (f2 << 4) | f3);
                        if (lo < 0xDC00 || lo > 0xDFFF) return false;
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        p += 6;
                    } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                        return false;
                    }
                    appendUtf8(out, cp);
                    break;
                }
                default: return false;
            }
        } else {
            out += c;
            p++;
        }
    }
    return true;
}

// End position just past one JSON value starting at p, or npos
// when malformed. Strings, objects, arrays, true/false/null and
// strict numbers are handled, with string state tracked so
// brackets inside strings never count as structure.
size_t jsonValueEnd(const std::string& s, size_t p) {
    p = skipWs(s, p);
    if (p >= s.size()) return std::string::npos;
    char c = s[p];
    if (c == '"') return jsonStringEnd(s, p);
    if (c == '{') {
        p++;
        p = skipWs(s, p);
        if (p < s.size() && s[p] == '}') return p + 1;
        while (true) {
            if (p >= s.size() || s[p] != '"') return std::string::npos;
            p = jsonStringEnd(s, p);
            if (p == std::string::npos) return std::string::npos;
            p = skipWs(s, p);
            if (p >= s.size() || s[p] != ':') return std::string::npos;
            p++;
            p = jsonValueEnd(s, p);
            if (p == std::string::npos) return std::string::npos;
            p = skipWs(s, p);
            if (p < s.size() && s[p] == ',') { p++; p = skipWs(s, p); continue; }
            if (p < s.size() && s[p] == '}') return p + 1;
            return std::string::npos;
        }
    }
    if (c == '[') {
        p++;
        p = skipWs(s, p);
        if (p < s.size() && s[p] == ']') return p + 1;
        while (true) {
            p = jsonValueEnd(s, p);
            if (p == std::string::npos) return std::string::npos;
            p = skipWs(s, p);
            if (p < s.size() && s[p] == ',') { p++; continue; }
            if (p < s.size() && s[p] == ']') return p + 1;
            return std::string::npos;
        }
    }
    if (s.compare(p, 4, "true") == 0) return p + 4;
    if (s.compare(p, 5, "false") == 0) return p + 5;
    if (s.compare(p, 4, "null") == 0) return p + 4;
    size_t q = p;
    if (q < s.size() && s[q] == '-') q++;
    if (q >= s.size() || !isdigit(static_cast<unsigned char>(s[q]))) return std::string::npos;
    if (s[q] == '0') {
        q++;
    } else {
        while (q < s.size() && isdigit(static_cast<unsigned char>(s[q]))) q++;
    }
    if (q < s.size() && s[q] == '.') {
        q++;
        if (q >= s.size() || !isdigit(static_cast<unsigned char>(s[q]))) return std::string::npos;
        while (q < s.size() && isdigit(static_cast<unsigned char>(s[q]))) q++;
    }
    if (q < s.size() && (s[q] == 'e' || s[q] == 'E')) {
        q++;
        if (q < s.size() && (s[q] == '+' || s[q] == '-')) q++;
        if (q >= s.size() || !isdigit(static_cast<unsigned char>(s[q]))) return std::string::npos;
        while (q < s.size() && isdigit(static_cast<unsigned char>(s[q]))) q++;
    }
    return q;
}

// Find a top-level field of a JSON object. `obj` must be a JSON
// object literal; returns false when it is not, or when the key
// is absent. On success `value` holds the raw (untrimmed) value
// text. Keys are decoded, so an escaped key still matches, and a
// key inside a string value can never match.
bool findTopField(const std::string& obj, const std::string& key, std::string& value) {
    size_t p = skipWs(obj, 0);
    if (p >= obj.size() || obj[p] != '{') return false;
    p++;
    p = skipWs(obj, p);
    if (p < obj.size() && obj[p] == '}') return false;
    while (true) {
        if (p >= obj.size() || obj[p] != '"') return false;
        size_t kend = jsonStringEnd(obj, p);
        if (kend == std::string::npos) return false;
        std::string k;
        if (!decodeJsonString(obj.substr(p, kend - p), k)) return false;
        p = skipWs(obj, kend);
        if (p >= obj.size() || obj[p] != ':') return false;
        p++;
        size_t vstart = skipWs(obj, p);
        size_t vend = jsonValueEnd(obj, vstart);
        if (vend == std::string::npos) return false;
        if (k == key) { value = obj.substr(vstart, vend - vstart); return true; }
        p = skipWs(obj, vend);
        if (p < obj.size() && obj[p] == ',') { p++; p = skipWs(obj, p); continue; }
        if (p < obj.size() && obj[p] == '}') return false;
        return false;
    }
}

// A raw value must be a JSON string literal; decodes it.
bool getStringField(const std::string& obj, const std::string& key, std::string& out) {
    std::string raw;
    if (!findTopField(obj, key, raw)) return false;
    size_t p = skipWs(raw, 0);
    size_t end = jsonStringEnd(raw, p);
    if (end == std::string::npos) return false;
    if (skipWs(raw, end) != raw.size()) return false;
    return decodeJsonString(raw.substr(p, end - p), out);
}

// A raw value must be exactly JSON `true`. findTopField already
// trims leading whitespace and ends the value right after it,
// so the raw text is exactly "true" or it is not.
bool getBoolField(const std::string& obj, const std::string& key) {
    std::string raw;
    if (!findTopField(obj, key, raw)) return false;
    return raw == "true";
}

// A raw value must be exactly one strict JSON integer (optional
// '-', digits only, nothing else).
bool getIntField(const std::string& obj, const std::string& key, long long& out) {
    std::string raw;
    if (!findTopField(obj, key, raw)) return false;
    size_t p = skipWs(raw, 0);
    size_t start = p;
    if (p < raw.size() && raw[p] == '-') p++;
    size_t digits = p;
    while (p < raw.size() && isdigit(static_cast<unsigned char>(raw[p]))) p++;
    if (p == digits) return false;
    if (skipWs(raw, p) != raw.size()) return false;
    try {
        out = std::stoll(raw.substr(start, p - start));
    } catch (...) {
        return false;
    }
    return true;
}

// ------------------------------------------------------------ JWKS fetch
const size_t kMaxJwksBytes = 1024 * 1024;  // 1 MiB cap on the key set

size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
    std::string* out = static_cast<std::string*>(userdata);
    size_t n = size * nmemb;
    if (out->size() + n > kMaxJwksBytes) return 0;  // abort: key set too large
    out->append(ptr, n);
    return n;
}

void initCurlOnce() {
    static std::once_flag flag;
    std::call_once(flag, []() { curl_global_init(CURL_GLOBAL_DEFAULT); });
}

// GET one URL (the JWKS endpoint). Returns false on any network
// or HTTP failure. The body is never logged.
bool fetchUrl(const std::string& url, std::string& body) {
    initCurlOnce();
    CURL* curl = curl_easy_init();
    if (curl == nullptr) return false;
    body.clear();
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPGET, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    CURLcode rc = curl_easy_perform(curl);
    long httpCode = 0;
    if (rc == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_easy_cleanup(curl);
    return rc == CURLE_OK && httpCode == 200;
}

// ------------------------------------------------------------ JWKS cache
struct JwkKey {
    std::string n;  // base64url modulus
    std::string e;  // base64url exponent
};

std::mutex g_jwksMutex;
std::map<std::string, JwkKey> g_jwksKeys;
long long g_jwksFetchedAt = 0;

// Parse a JWKS document into kid -> key. Only RSA keys with a
// kid, n and e are kept; anything else is ignored (a bad key in
// the set must not break verification of the good ones).
bool parseJwks(const std::string& body, std::map<std::string, JwkKey>& keys) {
    keys.clear();
    std::string rawArray;
    if (!findTopField(body, "keys", rawArray)) return false;
    size_t p = skipWs(rawArray, 0);
    if (p >= rawArray.size() || rawArray[p] != '[') return false;
    p++;
    while (true) {
        p = skipWs(rawArray, p);
        if (p >= rawArray.size()) return false;
        if (rawArray[p] == ']') return !keys.empty();
        size_t end = jsonValueEnd(rawArray, p);
        if (end == std::string::npos) return false;
        std::string elem = rawArray.substr(p, end - p);
        p = skipWs(rawArray, end);
        if (p < rawArray.size() && rawArray[p] == ',') p++;
        else if (p >= rawArray.size() || rawArray[p] != ']') return false;
        std::string kty, kid, n, e;
        if (!getStringField(elem, "kty", kty) || kty != "RSA") continue;
        if (!getStringField(elem, "kid", kid) || kid.empty()) continue;
        if (!getStringField(elem, "n", n) || n.empty()) continue;
        if (!getStringField(elem, "e", e) || e.empty()) continue;
        keys[kid] = JwkKey{n, e};
    }
}

// Fetch the JWKS and replace the cache. Returns false when the
// fetch or parse fails (the old cache is left untouched).
bool refreshJwks() {
    std::string body;
    if (!fetchUrl(jwksUrl(), body)) return false;
    std::map<std::string, JwkKey> keys;
    if (!parseJwks(body, keys)) return false;
    g_jwksKeys = keys;
    g_jwksFetchedAt = static_cast<long long>(std::time(nullptr));
    return true;
}

// ------------------------------------------------------------ RS256 verify
// Verify an RS256 signature with one JWK (n/e). Modern OpenSSL 3.0
// API (EVP_PKEY_fromdata) — no deprecated low-level RSA calls, so
// this compiles with -Wall -Wextra -Wpedantic and 0 warnings.
//
// The public key is built with the OSSL_PARAM_BLD API: BN_bin2bn
// turns the big-endian bytes into BIGNUMs and push_BN stores them
// as parameters. OSSL_PARAM_construct_BN was tried first and is NOT
// used: on this OpenSSL 3.0 build the key it builds has a different
// modulus than the one passed in (verified by reading the key back
// with EVP_PKEY_get_bn_param), so verification fails with a padding
// error even for a signature openssl itself verifies.
bool rsaVerify(const JwkKey& key, const std::string& signedData,
               const std::string& signature) {
    std::string nBytes, eBytes;
    if (!base64UrlDecode(key.n, nBytes) || !base64UrlDecode(key.e, eBytes)) return false;
    if (nBytes.empty() || eBytes.empty()) return false;

    BIGNUM* bnN = BN_bin2bn(reinterpret_cast<const unsigned char*>(nBytes.data()),
                            (int)nBytes.size(), nullptr);
    BIGNUM* bnE = BN_bin2bn(reinterpret_cast<const unsigned char*>(eBytes.data()),
                            (int)eBytes.size(), nullptr);
    if (bnN == nullptr || bnE == nullptr) {
        BN_free(bnN);
        BN_free(bnE);
        return false;
    }
    OSSL_PARAM_BLD* bld = OSSL_PARAM_BLD_new();
    if (bld == nullptr) {
        BN_free(bnN);
        BN_free(bnE);
        return false;
    }
    bool ok = false;
    EVP_PKEY* pkey = nullptr;
    if (OSSL_PARAM_BLD_push_BN(bld, OSSL_PKEY_PARAM_RSA_N, bnN) == 1 &&
        OSSL_PARAM_BLD_push_BN(bld, OSSL_PKEY_PARAM_RSA_E, bnE) == 1) {
        OSSL_PARAM* params = OSSL_PARAM_BLD_to_param(bld);
        if (params != nullptr) {
            EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new_from_name(nullptr, "RSA", nullptr);
            if (ctx != nullptr) {
                if (EVP_PKEY_fromdata_init(ctx) > 0 &&
                    EVP_PKEY_fromdata(ctx, &pkey, EVP_PKEY_PUBLIC_KEY, params) > 0 &&
                    pkey != nullptr) {
                    EVP_MD_CTX* md = EVP_MD_CTX_new();
                    if (md != nullptr) {
                        if (EVP_DigestVerifyInit(md, nullptr, EVP_sha256(), nullptr, pkey) == 1 &&
                            EVP_DigestVerifyUpdate(md, signedData.data(), signedData.size()) == 1 &&
                            EVP_DigestVerifyFinal(md,
                                                  reinterpret_cast<const unsigned char*>(signature.data()),
                                                  signature.size()) == 1) {
                            ok = true;
                        }
                        EVP_MD_CTX_free(md);
                    }
                }
                EVP_PKEY_CTX_free(ctx);
            }
            OSSL_PARAM_free(params);
        }
    }
    OSSL_PARAM_BLD_free(bld);
    BN_free(bnN);
    BN_free(bnE);
    if (pkey != nullptr) EVP_PKEY_free(pkey);
    return ok;
}

}  // namespace

bool available() { return true; }

Result verifyToken(const std::string& idToken) {
    Result r;
    if (!available()) {
        r.error = "unavailable";
        return r;
    }
    if (!enabled()) {
        r.error = "not_configured";
        return r;
    }
    if (idToken.empty() || idToken.size() > kMaxTokenChars) {
        r.error = "invalid_token";
        return r;
    }
    // Split header.payload.signature (exactly 3 non-empty parts).
    size_t d1 = idToken.find('.');
    size_t d2 = (d1 == std::string::npos) ? std::string::npos : idToken.find('.', d1 + 1);
    if (d1 == std::string::npos || d2 == std::string::npos ||
        idToken.find('.', d2 + 1) != std::string::npos ||
        d1 == 0 || d2 == d1 + 1 || d2 + 1 >= idToken.size()) {
        r.error = "invalid_token";
        return r;
    }
    std::string headerB64 = idToken.substr(0, d1);
    std::string payloadB64 = idToken.substr(d1 + 1, d2 - d1 - 1);
    std::string sigB64 = idToken.substr(d2 + 1);
    std::string headerJson, payloadJson, signature;
    if (!base64UrlDecode(headerB64, headerJson) ||
        !base64UrlDecode(payloadB64, payloadJson) ||
        !base64UrlDecode(sigB64, signature)) {
        r.error = "invalid_token";
        return r;
    }
    // Header: alg must be exactly RS256; kid must be present.
    std::string alg, kid;
    if (!getStringField(headerJson, "alg", alg) || alg != "RS256") {
        r.error = "wrong_algorithm";
        return r;
    }
    if (!getStringField(headerJson, "kid", kid) || kid.empty()) {
        r.error = "invalid_token";
        return r;
    }
    // Payload claims, all checked before the signature (a token
    // that fails a claim check is rejected without a JWKS fetch).
    Claims c;
    if (!getStringField(payloadJson, "sub", c.sub) || c.sub.empty()) {
        r.error = "invalid_token";
        return r;
    }
    if (!getStringField(payloadJson, "email", c.email) || c.email.empty()) {
        r.error = "invalid_token";
        return r;
    }
    if (!getStringField(payloadJson, "name", c.name)) c.name = "";
    std::string iss;
    if (!getStringField(payloadJson, "iss", iss) ||
        (iss != "https://accounts.google.com" && iss != "accounts.google.com")) {
        r.error = "wrong_issuer";
        return r;
    }
    // aud is a string (normal case) or an array of strings.
    std::string audRaw;
    bool audOk = false;
    if (findTopField(payloadJson, "aud", audRaw)) {
        std::string audStr;
        size_t p = skipWs(audRaw, 0);
        if (p < audRaw.size() && audRaw[p] == '"') {
            if (decodeJsonString(audRaw.substr(p, jsonStringEnd(audRaw, p) - p), audStr))
                audOk = (audStr == clientId());
        } else if (p < audRaw.size() && audRaw[p] == '[') {
            size_t q = p + 1;
            while (true) {
                q = skipWs(audRaw, q);
                if (q >= audRaw.size()) break;
                if (audRaw[q] == ']') break;
                size_t end = jsonStringEnd(audRaw, q);
                if (end == std::string::npos) break;
                std::string elem;
                if (decodeJsonString(audRaw.substr(q, end - q), elem) && elem == clientId())
                    audOk = true;
                q = skipWs(audRaw, end);
                if (q < audRaw.size() && audRaw[q] == ',') { q++; continue; }
                break;
            }
        }
    }
    if (!audOk) {
        r.error = "wrong_audience";
        return r;
    }
    long long exp = 0;
    if (!getIntField(payloadJson, "exp", exp) || exp <= 0) {
        r.error = "invalid_token";
        return r;
    }
    long long now = static_cast<long long>(std::time(nullptr));
    if (exp <= now - 60) {  // 60 s of clock-skew leeway
        r.error = "expired";
        return r;
    }
    c.exp = exp;
    if (!getBoolField(payloadJson, "email_verified")) {
        r.error = "email_not_verified";
        return r;
    }
    c.emailVerified = true;
    // Signature: look the kid up in the JWKS cache, refreshing
    // when the kid is unknown or the cache is stale. A refresh
    // that fails outright is "fetch_failed" (the keys could not
    // be fetched at all — try again later); a refresh that
    // succeeds but still has no such kid is "unknown_kid".
    JwkKey key;
    {
        std::lock_guard<std::mutex> lk(g_jwksMutex);
        auto it = g_jwksKeys.find(kid);
        if (it == g_jwksKeys.end() || now - g_jwksFetchedAt >= kJwksCacheSecs) {
            if (!refreshJwks()) {
                r.error = "fetch_failed";
                return r;
            }
            it = g_jwksKeys.find(kid);
            if (it == g_jwksKeys.end()) {
                r.error = "unknown_kid";
                return r;
            }
        }
        key = it->second;
    }
    std::string signedData = headerB64 + "." + payloadB64;
    if (!rsaVerify(key, signedData, signature)) {
        r.error = "bad_signature";
        return r;
    }
    r.ok = true;
    r.claims = c;
    return r;
}

#else  // !PDPS_HAVE_GOOGLE_AUTH — stub: server builds and runs without Google.

bool available() { return false; }

Result verifyToken(const std::string& /*idToken*/) {
    Result r;
    r.error = "unavailable";
    return r;
}

#endif  // PDPS_HAVE_GOOGLE_AUTH

}  // namespace google_auth
