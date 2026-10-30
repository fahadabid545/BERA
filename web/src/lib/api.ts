/** Talks to the server. Every failure arrives in the one shared shape: code, message, fields. */

export type ApiError = {
  code: string;
  message: string;
  fields?: Record<string, string>;
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

const UNREACHABLE: ApiError = {
  code: "unreachable",
  message: "We could not reach the server. Check your connection and try again.",
};

async function request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "same-origin", ...init });
  } catch {
    return { ok: false, error: UNREACHABLE };
  }
  const body = await response.json().catch(() => null);
  if (response.ok) return { ok: true, data: body as T };
  const error = body?.error as ApiError | undefined;
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
