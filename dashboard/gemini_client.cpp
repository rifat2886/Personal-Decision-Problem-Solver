// gemini_client.cpp — minimal Gemini API client (see gemini_client.h).
//
// The prompt is sent as data only: {"contents":[{"parts":[{"text":
// "<prompt>"}]}]}. The reply text is extracted from
// candidates[0].content.parts[0].text with a small hand-rolled JSON
// string parser (same style as cpp_server.cpp's minimal JSON
// helpers) — no full JSON parser is needed for this one field, and
// no prompt, key, or response body is ever logged or returned in
// an error.

#include "gemini_client.h"

#include <cstdlib>
#include <cstring>

#if !defined(PDPS_NO_CURL) && defined(__has_include)
#if __has_include(<curl/curl.h>)
#define PDPS_HAVE_CURL 1
#endif
#endif

#ifdef PDPS_HAVE_CURL
#include <curl/curl.h>
#include <mutex>
#endif

namespace gemini {

namespace {

// Default model and API base. Both are overridable by environment
// for tests (GEMINI_MODEL, GEMINI_API_BASE_URL); the key never is.
const char* kDefaultModel = "gemini-2.0-flash";
const size_t kMaxPromptChars = 8000;

std::string envOr(const char* name, const char* fallback) {
    const char* v = std::getenv(name);
    return (v != nullptr && v[0] != '\0') ? std::string(v) : std::string(fallback);
}

}  // namespace

bool configured() {
    const char* k = std::getenv("GEMINI_API_KEY");
    return k != nullptr && k[0] != '\0';
}

std::string modelName() {
    std::string m = envOr("GEMINI_MODEL", kDefaultModel);
    // The model name goes into the request URL, so only URL-safe
    // characters are allowed; anything else falls back to default.
    if (m.empty()) return kDefaultModel;
    for (char c : m) {
        bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
        if (!ok) return kDefaultModel;
    }
    return m;
}

#ifdef PDPS_HAVE_CURL

namespace {

// Default API base, overridable by GEMINI_API_BASE_URL for tests.
const char* kDefaultBaseUrl = "https://generativelanguage.googleapis.com/v1beta";
const size_t kMaxResponseBytes = 1024 * 1024;  // 1 MiB cap on replies

// Total request timeout in seconds: GEMINI_TIMEOUT_SECS, clamped
// to 1..120, default 30.
long timeoutSecs() {
    const char* v = std::getenv("GEMINI_TIMEOUT_SECS");
    if (v == nullptr || v[0] == '\0') return 30;
    long t = std::atol(v);
    if (t < 1) return 1;
    if (t > 120) return 120;
    return t;
}

std::string baseUrl() {
    std::string b = envOr("GEMINI_API_BASE_URL", kDefaultBaseUrl);
    while (!b.empty() && b.back() == '/') b.pop_back();
    return b.empty() ? std::string(kDefaultBaseUrl) : b;
}

// Escape a string for inclusion inside a JSON string literal.
std::string jsonEscape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 2);
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out += static_cast<char>(c);
                }
        }
    }
    return out;
}

// Append one Unicode code point as UTF-8.
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

// Parse one JSON string value starting at body[pos] (which must be
// the opening '"'). On success returns true, sets out to the
// unescaped value, and endPos to just past the closing quote.
bool parseJsonString(const std::string& body, size_t pos, std::string& out, size_t& endPos) {
    if (pos >= body.size() || body[pos] != '"') return false;
    pos++;
    out.clear();
    while (pos < body.size()) {
        char c = body[pos];
        if (c == '"') {
            endPos = pos + 1;
            return true;
        }
        if (c == '\\' && pos + 1 < body.size()) {
            char e = body[pos + 1];
            switch (e) {
                case '"': out += '"'; pos += 2; break;
                case '\\': out += '\\'; pos += 2; break;
                case '/': out += '/'; pos += 2; break;
                case 'b': out += '\b'; pos += 2; break;
                case 'f': out += '\f'; pos += 2; break;
                case 'n': out += '\n'; pos += 2; break;
                case 'r': out += '\r'; pos += 2; break;
                case 't': out += '\t'; pos += 2; break;
                case 'u': {
                    if (pos + 5 >= body.size()) return false;
                    unsigned cp = 0;
                    for (int i = 0; i < 4; i++) {
                        char h = body[pos + 2 + i];
                        cp <<= 4;
                        if (h >= '0' && h <= '9') cp |= static_cast<unsigned>(h - '0');
                        else if (h >= 'a' && h <= 'f') cp |= static_cast<unsigned>(h - 'a' + 10);
                        else if (h >= 'A' && h <= 'F') cp |= static_cast<unsigned>(h - 'A' + 10);
                        else return false;
                    }
                    pos += 6;
                    // Surrogate pair: high surrogate followed by \uXXXX low.
                    if (cp >= 0xD800 && cp <= 0xDBFF && pos + 5 < body.size() &&
                        body[pos] == '\\' && body[pos + 1] == 'u') {
                        unsigned lo = 0;
                        bool okHex = true;
                        for (int i = 0; i < 4; i++) {
                            char h = body[pos + 2 + i];
                            lo <<= 4;
                            if (h >= '0' && h <= '9') lo |= static_cast<unsigned>(h - '0');
                            else if (h >= 'a' && h <= 'f') lo |= static_cast<unsigned>(h - 'a' + 10);
                            else if (h >= 'A' && h <= 'F') lo |= static_cast<unsigned>(h - 'A' + 10);
                            else okHex = false;
                        }
                        if (okHex && lo >= 0xDC00 && lo <= 0xDFFF) {
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                            pos += 6;
                        }
                    }
                    appendUtf8(out, cp);
                    break;
                }
                default: return false;
            }
        } else if (static_cast<unsigned char>(c) < 0x20) {
            return false;  // raw control character inside a string
        } else {
            out += c;
            pos++;
        }
    }
    return false;  // unterminated string
}

// Extract candidates[0].content.parts[0].text from a generateContent
// response. Only the first text part is used; anything else in the
// body is ignored. Returns false when the shape is missing or the
// text is empty.
bool extractReplyText(const std::string& body, std::string& out) {
    size_t p = body.find("\"candidates\"");
    if (p == std::string::npos) return false;
    p = body.find("\"parts\"", p);
    if (p == std::string::npos) return false;
    p = body.find("\"text\"", p);
    if (p == std::string::npos) return false;
    p = body.find(':', p + 6);
    if (p == std::string::npos) return false;
    p++;
    while (p < body.size() && (body[p] == ' ' || body[p] == '\t' ||
                               body[p] == '\n' || body[p] == '\r'))
        p++;
    size_t endPos = 0;
    if (!parseJsonString(body, p, out, endPos)) return false;
    return !out.empty();
}

size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
    std::string* out = static_cast<std::string*>(userdata);
    size_t n = size * nmemb;
    if (out->size() + n > kMaxResponseBytes) return 0;  // abort: reply too large
    out->append(ptr, n);
    return n;
}

void initCurlOnce() {
    static std::once_flag flag;
    std::call_once(flag, []() { curl_global_init(CURL_GLOBAL_DEFAULT); });
}

}  // namespace

bool available() { return true; }

Result generate(const std::string& prompt) {
    Result r;
    if (prompt.empty() || prompt.size() > kMaxPromptChars) {
        r.error = "invalid_request";
        return r;
    }
    if (!available()) {
        r.error = "unavailable";
        return r;
    }
    // The key is read fresh here and used only as a request header
    // below. It is never stored, logged, or included in any error.
    const char* key = std::getenv("GEMINI_API_KEY");
    if (key == nullptr || key[0] == '\0') {
        r.error = "not_configured";
        return r;
    }
    initCurlOnce();

    std::string url = baseUrl() + "/models/" + modelName() + ":generateContent";
    std::string reqBody = "{\"contents\":[{\"parts\":[{\"text\":\"" +
                          jsonEscape(prompt) + "\"}]}]}";

    CURL* curl = curl_easy_init();
    if (curl == nullptr) {
        r.error = "request_failed";
        return r;
    }
    std::string respBody;
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    std::string authHeader = std::string("x-goog-api-key: ") + key;
    headers = curl_slist_append(headers, authHeader.c_str());

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, reqBody.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(reqBody.size()));
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &respBody);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeoutSecs());
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);  // server is multithreaded
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);

    CURLcode rc = curl_easy_perform(curl);
    long httpCode = 0;
    if (rc == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (rc == CURLE_OPERATION_TIMEDOUT) {
        r.error = "timeout";
        return r;
    }
    if (rc != CURLE_OK) {
        r.error = "request_failed";
        return r;
    }
    if (httpCode == 401 || httpCode == 403) {
        r.error = "auth_error";
        return r;
    }
    if (httpCode < 200 || httpCode >= 300) {
        r.error = "request_failed";
        return r;
    }
    std::string text;
    if (!extractReplyText(respBody, text)) {
        r.error = "invalid_response";
        return r;
    }
    r.ok = true;
    r.text = text;
    return r;
}

#else  // !PDPS_HAVE_CURL — stub: server builds and runs without Gemini.

bool available() { return false; }

Result generate(const std::string& prompt) {
    Result r;
    if (prompt.empty() || prompt.size() > kMaxPromptChars) {
        r.error = "invalid_request";
        return r;
    }
    r.error = "unavailable";
    return r;
}

#endif  // PDPS_HAVE_CURL

}  // namespace gemini
