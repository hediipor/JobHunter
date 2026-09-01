const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = {
  get: (path: string) => fetch(`${BACKEND}${path}`).then(r => r.json()),
  post: (path: string, body?: unknown) =>
    fetch(`${BACKEND}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then(r => r.json()),
  patch: (path: string, body: unknown) =>
    fetch(`${BACKEND}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(r => r.json()),
  delete: (path: string) =>
    fetch(`${BACKEND}${path}`, { method: "DELETE" }).then(r => r.json()),
  put: (path: string, body: unknown) =>
    fetch(`${BACKEND}${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(r => r.json()),
};

export default api;
export const API_BASE = BACKEND;
