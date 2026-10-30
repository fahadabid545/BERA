import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { logOut, logOutEverywhere } from "./logout";

const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({
  navigateTo: (address: string) => navigateTo(address),
  currentAddress: () => window.location.pathname,
}));

function stubServer(reply: Response | "down" = new Response("{}", { status: 200 })) {
  const fetchMock = vi.fn(async () => {
    if (reply === "down") throw new TypeError("network down");
    return reply;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  navigateTo.mockClear();
  window.history.pushState({}, "", "/company");
});
afterEach(() => vi.unstubAllGlobals());

describe("logging out", () => {
  it("ends the session on the server, then shows the login page", async () => {
    const server = stubServer();
    await logOut();
    expect((server.mock.calls[0] as unknown as [string, RequestInit])[0]).toBe(
      "/api/auth/company/logout/",
    );
    expect(navigateTo).toHaveBeenCalledWith("/login");
  });

  it("signs out of all devices through its own route", async () => {
    const server = stubServer();
    await logOutEverywhere();
    expect((server.mock.calls[0] as unknown as [string])[0]).toBe("/api/auth/company/logout-all/");
    expect(navigateTo).toHaveBeenCalledWith("/login");
  });

  it("uses the admin routes and login page in the admin area", async () => {
    window.history.pushState({}, "", "/admin");
    const server = stubServer();
    await logOut();
    expect((server.mock.calls[0] as unknown as [string])[0]).toBe("/api/auth/admin/logout/");
    expect(navigateTo).toHaveBeenCalledWith("/admin/login");
  });

  it("still leaves the page when the server cannot be reached", async () => {
    stubServer("down");
    await logOut();
    expect(navigateTo).toHaveBeenCalledWith("/login");
  });
});
