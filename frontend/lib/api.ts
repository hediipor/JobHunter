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

const api = {
  get: (path: string) => fetch(url(path)).then(r => r.json()),
  post: (path: string, body?: unknown) =>
    fetch(url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then(r => r.json()),
  patch: (path: string, body: unknown) =>
    fetch(url(path), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(r => r.json()),
  delete: (path: string) =>
    fetch(url(path), { method: "DELETE" }).then(r => r.json()),
  put: (path: string, body: unknown) =>
    fetch(url(path), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(r => r.json()),
};

export default api;
export const API_BASE = BACKEND;
