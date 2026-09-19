// Dev (`next dev` on :3000) talks to the backend on a different origin (:8000),
// so it needs an absolute URL. The packaged/static build is always served BY
// the same FastAPI process it calls (see backend/main.py's static mount) —
// same origin, so a relative path works regardless of which port that process
// picked (backend/launcher.py's _free_port can land on 8001+ if 8000's busy).
const BACKEND =
  process.env.NEXT_PUBLIC_API_URL ??
  (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

// All backend API routes live under /api (see backend/main.py) — kept out of
// API_BASE itself since that's also used bare for /files/... PDF links.
const url = (path: string) => `${BACKEND}/api${path}`;

// Non-2xx throws, with FastAPI's `detail` as the message — so a 503 "out of
// quota" lands in onError instead of being parsed as a success payload.
async function call(path: string, method = "GET", body?: unknown) {
  const r = await fetch(url(path), {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const d = data?.detail;
    throw new Error(typeof d === "string" ? d : `${r.status} ${r.statusText}`);
  }
  return data;
}

const api = {
  get: (path: string) => call(path),
  post: (path: string, body?: unknown) => call(path, "POST", body),
  patch: (path: string, body: unknown) => call(path, "PATCH", body),
  delete: (path: string) => call(path, "DELETE"),
  put: (path: string, body: unknown) => call(path, "PUT", body),
};

export default api;
export const API_BASE = BACKEND;
