import { currentKind, sessionEnded } from "@/lib/session";

/** Talks to the server. Every failure arrives in the one shared shape: code, message, fields. */

export type ApiError = {
  code: string;
  message: string;
  fields?: Record<string, string>;
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

const NOT_SIGNED_IN = "not_signed_in";
const UNREACHABLE: ApiError = {
  code: "unreachable",
  message: "We could not reach the server. Check your connection and try again.",
};

const CSRF_COOKIE = "bera_csrf";
const SAFE_METHODS = ["GET", "HEAD", "OPTIONS"];

/** The server asks changing requests to repeat this readable cookie in a header. */
function csrfHeader(method: string): Record<string, string> {
  if (SAFE_METHODS.includes(method)) return {};
  const found = document.cookie.split("; ").find((cookie) => cookie.startsWith(`${CSRF_COOKIE}=`));
  return found ? { "X-CSRF-Token": found.slice(CSRF_COOKIE.length + 1) } : {};
}

async function send(path: string, init: RequestInit): Promise<Response> {
  const method = init.method ?? "GET";
  const headers = { ...csrfHeader(method), ...(init.headers as Record<string, string>) };
  return fetch(path, { credentials: "same-origin", ...init, headers });
}

/** Asks for a new short-lived sign-in using the long-lived one. True if it worked. */
async function renewSession(): Promise<boolean> {
  try {
    const response = await send(`/api/auth/${currentKind()}/refresh/`, { method: "POST" });
    return response.ok;
  } catch {
    return false;
  }
}

async function request<T>(path: string, init: RequestInit, mayRenew = true): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await send(path, init);
  } catch {
    return { ok: false, error: UNREACHABLE };
  }
  const body = await response.json().catch(() => null);
  if (response.ok) return { ok: true, data: body as T };
  const error = body?.error as ApiError | undefined;
  if (response.status === 401 && error?.code === NOT_SIGNED_IN) {
    // The short-lived sign-in ended while the person was working: renew it and carry on once.
    if (mayRenew && (await renewSession())) return request<T>(path, init, false);
    sessionEnded();
  }
  return {
    ok: false,
    error: error ?? { code: "internal_error", message: "Something went wrong." },
  };
}

export function getJson<T>(path: string) {
  return request<T>(path, { method: "GET" });
}

export function postJson<T>(path: string, body: unknown) {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
