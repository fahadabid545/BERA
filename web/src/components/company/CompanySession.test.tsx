import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanySession } from "./CompanySession";

const pathname = { current: "/company" };
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));
const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({
  navigateTo: (address: string) => navigateTo(address),
  currentAddress: () => "/company/team",
}));

type Reply = { status?: number; body: unknown };

function stubMe(reply: Reply | (() => Reply)) {
  const fetchMock = vi.fn(async (path: string) => {
    // The top-bar meter reads its own figures; these tests are about the session.
    if (path === "/api/company/usage/") {
      return new Response(JSON.stringify({ error: { code: "x", message: "x" } }), { status: 403 });
    }
    const { status = 200, body } = typeof reply === "function" ? reply() : reply;
    return new Response(JSON.stringify(body), { status });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const ME = (role: string) => ({
  body: { name: "Fake Person", company_name: "Fake Test Company", role },
});

const sidebar = () => screen.getByRole("navigation", { name: "Company" });

beforeEach(() => {
  pathname.current = "/company";
  navigateTo.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe("company session", () => {
  it("shows the real company and name, and an owner the whole menu", async () => {
    stubMe(ME("owner"));
    render(<CompanySession>Page content</CompanySession>);
    expect(await screen.findByText("Fake Test Company")).toBeTruthy();
    expect(sidebar().textContent).toContain("Team");
    expect(sidebar().textContent).toContain("Advanced");
    expect(screen.getByRole("main").textContent).toBe("Page content");
  });

  it("shows a member only their own menu", async () => {
    stubMe(ME("member"));
    render(<CompanySession>Page content</CompanySession>);
    await screen.findByText("Fake Test Company");
    expect(sidebar().textContent).toContain("Projects");
    for (const hidden of ["Team", "Usage and Billing", "Settings", "Advanced"]) {
      expect(sidebar().textContent).not.toContain(hidden);
    }
  });

  it("shows nothing of the area while it does not know who is signed in", () => {
    stubMe(ME("owner"));
    render(<CompanySession>Page content</CompanySession>);
    expect(screen.queryByText("Page content")).toBeNull();
  });

  it("sends a signed-out person to the login page, back to where they were", async () => {
    stubMe({
      status: 401,
      body: { error: { code: "not_signed_in", message: "You are not signed in." } },
    });
    render(<CompanySession>Page content</CompanySession>);
    await waitFor(() => expect(navigateTo).toHaveBeenCalledWith("/login?next=%2Fcompany%2Fteam"));
    expect(screen.queryByText("Page content")).toBeNull();
  });

  it("says plainly when the server cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("down");
      }),
    );
    render(<CompanySession>Page content</CompanySession>);
    expect((await screen.findByRole("alert")).textContent).toContain("could not reach");
  });

  it("reads the role again on the next page, so a role change applies at once", async () => {
    let role = "owner";
    stubMe(() => ME(role));
    const { rerender } = render(<CompanySession>Page content</CompanySession>);
    await screen.findByText("Fake Test Company");
    expect(sidebar().textContent).toContain("Team");

    role = "member";
    pathname.current = "/company/projects";
    rerender(<CompanySession>Page content</CompanySession>);
    await waitFor(() => expect(sidebar().textContent).not.toContain("Team"));
  });

  it("shows a member who was demoted on an owner page the no-access page", async () => {
    pathname.current = "/company/team";
    stubMe(ME("member"));
    render(<CompanySession>Page content</CompanySession>);
    expect(await screen.findByRole("heading", { name: "You do not have access" })).toBeTruthy();
    expect(screen.queryByText("Page content")).toBeNull();
  });
});
