import axios from "axios";

// Same-origin relative base: works from ANY preview/deployment URL the app is
// served on (ingress routes /api/* to the backend). Avoids CORS/cookie issues
// when the external hostname rotates.
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

export function apiError(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || "").filter(Boolean).join(" ");
  return e?.message || "Something went wrong";
}
