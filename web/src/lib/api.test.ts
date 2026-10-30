import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getJson, postJson } from "./api";
import { startUpload } from "./session";

const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({
  navigateTo: (address: string) => navigateTo(address),
  currentAddress: () => window.location.pathname + window.location.search,
}));

type Reply = { status: number; body: unknown };
const NOT_SIGNED_IN: Reply = {
  status: 401,
  body: { error: { code: "not_signed_in", message: "You are not signed in." } },
};
const OK: Reply = { status: 200, body: { fine: true } };

/** Answers each request in turn with the next reply. */
function serverAnswering(...replies: Reply[]) {
  const queue = [...replies];
  const fetchMock = vi.fn(async () => {
    const reply = queue.shift() ?? OK;
    return new Response(JSON.stringify(reply.body), { status: reply.status });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const calledPaths = (fetchMock: ReturnType<typeof serverAnswering>) =>
  fetchMock.mock.calls.map((call) => (call as unknown as [string])[0]);

beforeEach(() => {
  navigateTo.mockClear();
  window.history.pushState({}, "", "/company/projects?tab=2");
  document.cookie = "bera_csrf=csrf-from-cookie; path=/";
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "bera_csrf=; path=/; max-age=0";
});

describe("the protection against other websites", () => {
  it("repeats the readable cookie in a header on changing requests", async () => {
    const server = serverAnswering(OK);
    await postJson("/api/things/", {});
    const init = (server.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-from-cookie");
  });

  it("does not add it to reading requests", async () => {
    const server = serverAnswering(OK);
    await getJson("/api/things/");
    const init = (server.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });
});

describe("a session that ends while the person works", () => {
  it("is renewed quietly and the request is repeated once", async () => {
    const server = serverAnswering(NOT_SIGNED_IN, OK, OK);
    const result = await getJson("/api/things/");
    expect(result).toEqual({ ok: true, data: { fine: true } });
    expect(calledPaths(server)).toEqual([
      "/api/things/",
      "/api/auth/company/refresh/",
      "/api/things/",
    ]);
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it("sends the person to log in, and back to the same page, when it cannot be renewed", async () => {
    serverAnswering(NOT_SIGNED_IN, NOT_SIGNED_IN);
    const result = await getJson("/api/things/");
    expect(result.ok).toBe(false);
    expect(navigateTo).toHaveBeenCalledWith("/login?next=%2Fcompany%2Fprojects%3Ftab%3D2");
  });

  it("goes to log in when it is still refused after being renewed", async () => {
    const server = serverAnswering(NOT_SIGNED_IN, OK, NOT_SIGNED_IN);
    await getJson("/api/things/");
    expect(calledPaths(server)).toHaveLength(3); // no endless retrying
    expect(navigateTo).toHaveBeenCalledTimes(1);
  });

  it("goes to log in when the server cannot be reached for the renewal", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(NOT_SIGNED_IN.body), { status: 401 }))
      .mockRejectedValueOnce(new TypeError("network down"));
    vi.stubGlobal("fetch", fetchMock);
    await getJson("/api/things/");
    expect(navigateTo).toHaveBeenCalledTimes(1);
  });

  it("renews the admin session in the admin area and returns to the admin login", async () => {
    window.history.pushState({}, "", "/admin/users");
    const server = serverAnswering(NOT_SIGNED_IN, NOT_SIGNED_IN);
    await getJson("/api/things/");
    expect(calledPaths(server)[1]).toBe("/api/auth/admin/refresh/");
    expect(navigateTo).toHaveBeenCalledWith("/admin/login");
  });

  it("does not leave the page while files are uploading, but warns", async () => {
    const warn = vi.fn();
    const { onUploadsAtRisk } = await import("./session");
    onUploadsAtRisk(warn);
    const finish = startUpload();
    serverAnswering(NOT_SIGNED_IN, NOT_SIGNED_IN);
    await getJson("/api/things/");
    expect(warn).toHaveBeenCalledTimes(1);
    expect(navigateTo).not.toHaveBeenCalled();
    finish();
    onUploadsAtRisk(null);
  });
});

describe("other failures", () => {
  it.each([
    [400, "validation_error"],
    [403, "not_allowed"],
    [404, "not_found"],
    [429, "too_many_requests"],
    [500, "internal_error"],
  ])("a %s (%s) does not renew or leave the page", async (status, code) => {
    const server = serverAnswering({ status, body: { error: { code, message: "x" } } });
    const result = await getJson("/api/things/");
    expect(result.ok).toBe(false);
    expect(calledPaths(server)).toEqual(["/api/things/"]);
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it("a 401 that is not about the session (such as a refused renewal) does not loop", async () => {
    const server = serverAnswering({
      status: 401,
      body: { error: { code: "something_else", message: "x" } },
    });
    await getJson("/api/things/");
    expect(calledPaths(server)).toEqual(["/api/things/"]);
  });
});
