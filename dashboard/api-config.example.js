// api-config.example.js — Route 2, Phase 1 (DO NOT commit a real copy
// with a backend URL as api-config.js unless your deployment needs
// direct Render calls; the recommended production path is a Vercel
// /api proxy rewrite, which needs no frontend change at all).
//
// To use a direct Render backend, copy this file to
// dashboard/api-config.js, set the Render service origin below, and
// add this line to dashboard/index.html BEFORE the app.js script:
//   <script src="api-config.js"></script>
//
// The value must be a plain https origin. It must NEVER be a
// DATABASE_URL, password, API key, or any other secret.

window.PDPS_API_BASE = "";
