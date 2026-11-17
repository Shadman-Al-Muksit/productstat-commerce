import type { components } from "./schema";

export type User = components["schemas"]["User"];
export type SKU = components["schemas"]["SKU"];
export type Product = components["schemas"]["Product"];
export type Bootstrap = components["schemas"]["Bootstrap"];
export type Cart = components["schemas"]["CartResult"];
export type Order = components["schemas"]["Order"];

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : flatten(detail));
  }
}
function flatten(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(flatten).join(" ");
  if (value && typeof value === "object")
    return Object.entries(value)
      .map(
        ([k, v]) =>
          `${k === "detail" || k === "error" ? "" : `${k}: `}${flatten(v)}`,
      )
      .join(" · ");
  return String(value ?? "Request failed");
}
let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}
export async function api<T = Record<string, unknown>>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method || "GET";
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) {
    const cookie =
      typeof document !== "undefined"
        ? document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1]
        : "";
    headers.set("X-CSRFToken", cookie ? decodeURIComponent(cookie) : csrf);
  }
  const response = await fetch(`/api/v1/${path.replace(/^\//, "")}`, {
    credentials: "include",
    cache: "no-store",
    ...options,
    headers,
  });
  const value =
    response.status === 204
      ? {}
      : await response.json().catch(() => ({
          detail: `Server returned ${response.status}. Please try again.`,
        }));
  if (!response.ok) throw new ApiError(response.status, value);
  return value as T;
}
export function list<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const r = value as Record<string, unknown>;
    return (r.results || r.items || r.products || []) as T[];
  }
  return [];
}
export function money(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `৳${new Intl.NumberFormat("en-BD", { maximumFractionDigits: 2 }).format(n)}`;
}
export function num(value: unknown): string {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    !Number.isFinite(Number(value))
  )
    return "—";
  return new Intl.NumberFormat("en-BD", { maximumFractionDigits: 1 }).format(
    Number(value ?? 0),
  );
}
export function pretty(value: unknown): string {
  return String(value ?? "—").replaceAll("_", " ");
}
