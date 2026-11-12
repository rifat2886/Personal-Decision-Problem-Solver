#ifndef PASSWORD_HASH_H
#define PASSWORD_HASH_H

// Password hashing for users.txt, shared by the console app and the
// C++ dashboard server (the Python fallback implements the identical
// format with hashlib.pbkdf2_hmac).
//
// Format (one field, no spaces, so the existing 3-field users.txt
// parsing "username credential ROLE" keeps working unchanged):
//   pbkdf2$100000$<salt-hex 32 chars>$<hash-hex 64 chars>
// where hash = PBKDF2-HMAC-SHA256(password, salt-bytes, 100000, 32 bytes).
// PBKDF2-HMAC-SHA256 is a recognised, standard password KDF (RFC 8018).
// Argon2id would need an external library, which this project does not
// depend on; PBKDF2 with 100k iterations is the stdlib-compatible choice
// that Python's hashlib can reproduce exactly.
//
// Migration (backward compatible, no silent format break):
// - New registrations store only the hash, never plaintext.
// - On login, a stored plaintext credential that matches is accepted
//   once and immediately rewritten as a hash (upgrade on login), under
//   the users.txt lock. After that login, no plaintext remains for
//   that user. Old accounts therefore keep working, and new accounts
//   are never plaintext.
// - Password change always stores the new password as a hash.
// - Hashes are never returned by any API (admin/users return
//   username + role only) and never logged.

#include <array>
#include <cstdint>
#include <random>
#include <sstream>
#include <string>
#include <vector>

namespace pdps_hash {

inline std::array<std::uint32_t, 64> kTable() {
    return {0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b,
            0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
            0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7,
            0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
            0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152,
            0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
            0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
            0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
            0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
            0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
            0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
            0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
            0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
}

inline std::uint32_t rotr(std::uint32_t x, int n) {
    return (x >> n) | (x << (32 - n));
}

inline std::vector<unsigned char> sha256(
    const unsigned char* data, std::size_t len) {
    std::uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                          0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    std::vector<unsigned char> msg(data, data + len);
    std::uint64_t bits = static_cast<std::uint64_t>(len) * 8;
    msg.push_back(0x80);
    while ((msg.size() % 64) != 56) msg.push_back(0);
    for (int i = 7; i >= 0; --i)
        msg.push_back(static_cast<unsigned char>((bits >> (i * 8)) & 0xff));
    auto table = kTable();
    for (std::size_t off = 0; off < msg.size(); off += 64) {
        std::uint32_t w[64];
        for (int i = 0; i < 16; ++i)
            w[i] = (static_cast<std::uint32_t>(msg[off + i * 4]) << 24) |
                   (static_cast<std::uint32_t>(msg[off + i * 4 + 1]) << 16) |
                   (static_cast<std::uint32_t>(msg[off + i * 4 + 2]) << 8) |
                   static_cast<std::uint32_t>(msg[off + i * 4 + 3]);
        for (int i = 16; i < 64; ++i) {
            std::uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^
                               (w[i - 15] >> 3);
            std::uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^
                               (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        std::uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4],
                      f = h[5], g = h[6], hh = h[7];
        for (int i = 0; i < 64; ++i) {
            std::uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            std::uint32_t ch = (e & f) ^ ((~e) & g);
            std::uint32_t t1 = hh + s1 + ch + table[i] + w[i];
            std::uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            std::uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
            std::uint32_t t2 = s0 + mj;
            hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d;
        h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    }
    std::vector<unsigned char> out(32);
    for (int i = 0; i < 8; ++i) {
        out[i * 4] = static_cast<unsigned char>((h[i] >> 24) & 0xff);
        out[i * 4 + 1] = static_cast<unsigned char>((h[i] >> 16) & 0xff);
        out[i * 4 + 2] = static_cast<unsigned char>((h[i] >> 8) & 0xff);
        out[i * 4 + 3] = static_cast<unsigned char>(h[i] & 0xff);
    }
    return out;
}

inline std::vector<unsigned char> hmacSha256(
    const std::vector<unsigned char>& key,
    const std::vector<unsigned char>& msg) {
    std::vector<unsigned char> k = key;
    if (k.size() > 64) {
        auto h = sha256(k.data(), k.size());
        k.assign(h.begin(), h.end());
    }
    k.resize(64, 0);
    std::vector<unsigned char> ipad(64), opad(64);
    for (int i = 0; i < 64; ++i) {
        ipad[i] = k[i] ^ 0x36;
        opad[i] = k[i] ^ 0x5c;
    }
    std::vector<unsigned char> inner = ipad;
    inner.insert(inner.end(), msg.begin(), msg.end());
    auto innerHash = sha256(inner.data(), inner.size());
    std::vector<unsigned char> outer = opad;
    outer.insert(outer.end(), innerHash.begin(), innerHash.end());
    return sha256(outer.data(), outer.size());
}

inline std::vector<unsigned char> pbkdf2(
    const std::string& password, const std::vector<unsigned char>& salt,
    int iterations, std::size_t dkLen) {
    std::vector<unsigned char> pw(password.begin(), password.end());
    std::vector<unsigned char> out;
    std::uint32_t block = 1;
    while (out.size() < dkLen) {
        std::vector<unsigned char> msg = salt;
        msg.push_back(static_cast<unsigned char>((block >> 24) & 0xff));
        msg.push_back(static_cast<unsigned char>((block >> 16) & 0xff));
        msg.push_back(static_cast<unsigned char>((block >> 8) & 0xff));
        msg.push_back(static_cast<unsigned char>(block & 0xff));
        auto u = hmacSha256(pw, msg);
        auto t = u;
        for (int i = 1; i < iterations; ++i) {
            u = hmacSha256(pw, u);
            for (std::size_t j = 0; j < t.size(); ++j) t[j] ^= u[j];
        }
        out.insert(out.end(), t.begin(), t.end());
        ++block;
    }
    out.resize(dkLen);
    return out;
}

inline std::string toHex(const std::vector<unsigned char>& bytes) {
    static const char* hex = "0123456789abcdef";
    std::string s;
    for (unsigned char b : bytes) {
        s += hex[b >> 4];
        s += hex[b & 0x0f];
    }
    return s;
}

inline bool fromHex(const std::string& hex,
                    std::vector<unsigned char>& out) {
    if (hex.size() % 2 != 0) return false;
    out.clear();
    auto val = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (std::size_t i = 0; i < hex.size(); i += 2) {
        int hi = val(hex[i]), lo = val(hex[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back(static_cast<unsigned char>((hi << 4) | lo));
    }
    return true;
}

inline bool isHashed(const std::string& stored) {
    return stored.rfind("pbkdf2$", 0) == 0;
}

inline std::string hashPassword(const std::string& password) {
    std::random_device rd;
    std::vector<unsigned char> salt(16);
    for (auto& b : salt) b = static_cast<unsigned char>(rd() & 0xff);
    auto dk = pbkdf2(password, salt, 100000, 32);
    return "pbkdf2$100000$" + toHex(salt) + "$" + toHex(dk);
}

inline bool verifyPassword(const std::string& password,
                           const std::string& stored) {
    // Google-only accounts (NULL password_hash) and the txt sentinel
    // must never authenticate: refuse an empty or sentinel credential.
    if (stored.empty() || stored == "!") return false;
    if (!isHashed(stored)) return password == stored;
    // pbkdf2$iterations$saltHex$hashHex
    std::vector<std::string> parts;
    std::size_t start = 0;
    while (true) {
        std::size_t pos = stored.find('$', start);
        if (pos == std::string::npos) {
            parts.push_back(stored.substr(start));
            break;
        }
        parts.push_back(stored.substr(start, pos - start));
        start = pos + 1;
    }
    if (parts.size() != 4 || parts[0] != "pbkdf2") return false;
    int iterations = 0;
    try {
        iterations = std::stoi(parts[1]);
    } catch (...) {
        return false;
    }
    if (iterations < 1 || iterations > 1000000) return false;
    std::vector<unsigned char> salt;
    if (!fromHex(parts[2], salt) || salt.empty()) return false;
    auto dk = pbkdf2(password, salt, iterations, 32);
    std::string got = toHex(dk);
    if (got.size() != parts[3].size()) return false;
    int diff = 0;
    for (std::size_t i = 0; i < got.size(); ++i)
        diff |= (got[i] ^ parts[3][i]);
    return diff == 0;
}

}  // namespace pdps_hash

#endif
