import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompanyTopBar } from "./CompanyTopBar";
import { UsageMeter, type PlanAndUsage } from "./UsageMeter";

const SUMMARY: PlanAndUsage = {
  plan_name: "Fake Plan",
  free_access: null,
  state: "active",
  period_start: "2030-01-15T00:00:00Z",
  period_end: "2030-02-15T00:00:00Z",
  cvs: { used: 3, limit: 10, left: 7, warning: null },
  estimated_cost: "0.012345",
  projects: { used: 0, limit: 3 },
  refresh_seconds: 3,
};

function stubServer(summary: PlanAndUsage | (() => PlanAndUsage) = SUMMARY, status = 200) {
  const fetchMock = vi.fn(async () => {
    const body = typeof summary === "function" ? summary() : summary;
    return new Response(
      JSON.stringify(status === 200 ? body : { error: { code: "x", message: "x" } }),
      {
        status,
      },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("beta access", () => {
  const BETA: PlanAndUsage = {
    ...SUMMARY,
    plan_name: null,
    state: "granted_free",
    free_access: {
      kind: "beta",
      ends_at: "2030-03-01T00:00:00Z",
      cvs_today: { used: 2, limit: 5 },
    },
  };

  it("shows the end date next to the meter and the CVs of today in the popup", async () => {
    stubServer(BETA);
    render(<UsageMeter />);
    expect(await screen.findByText("Beta until 1 Mar 2030")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /CVs 3/ }));
    const text = screen.getByRole("dialog", { name: "Plan and usage" }).textContent ?? "";
    expect(text).toContain("Beta access ends1 Mar 2030");
    expect(text).toContain("CVs today2 of 5");
  });

  it("shows no beta end date for a paying company or permitted access", async () => {
    stubServer({ ...BETA, free_access: { kind: "permitted", ends_at: null } });
    render(<UsageMeter />);
    await screen.findByRole("button", { name: /CVs 3/ });
    expect(screen.queryByText(/Beta until/)).toBeNull();
  });
});

describe("the small meter", () => {
  it("shows the CVs used against the limit", async () => {
    stubServer();
    render(<UsageMeter />);
    expect(await screen.findByRole("button", { name: /CVs 3 \/ 10/ })).toBeTruthy();
    expect(
      screen.getByRole("meter", { name: "CVs used this period" }).getAttribute("aria-valuenow"),
    ).toBe("3");
  });

  it("opens a popup with plan, period, CVs, cost and projects", async () => {
    stubServer();
    render(<UsageMeter />);
    await userEvent.click(await screen.findByRole("button", { name: /CVs 3/ }));
    const popup = screen.getByRole("dialog", { name: "Plan and usage" });
    const text = popup.textContent ?? "";
    expect(text).toContain("Fake Plan (Active)");
    expect(text).toContain("15 Jan 2030 to 15 Feb 2030");
    expect(text).toContain("3 of 10, 7 left");
    expect(text).toContain("$0.012345");
    expect(text).toContain("0 of 3");
  });

  it("shows nothing when the numbers cannot be read", async () => {
    const fetchMock = stubServer(SUMMARY, 403);
    render(<UsageMeter />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows a plan-less company as No plan", async () => {
    stubServer({ ...SUMMARY, plan_name: null, state: "no_plan" });
    render(<UsageMeter />);
    await userEvent.click(await screen.findByRole("button", { name: /CVs/ }));
    expect(within(screen.getByRole("dialog")).getByText("No plan")).toBeTruthy();
  });
});

describe("warnings", () => {
  it("shows no warning below 80 percent", async () => {
    stubServer();
    render(<UsageMeter />);
    await screen.findByRole("button");
    expect(screen.queryByText(/% used|limit reached/i)).toBeNull();
  });

  it("warns in words at 80 percent of CVs", async () => {
    stubServer({ ...SUMMARY, cvs: { used: 8, limit: 10, left: 2, warning: 80 } });
    render(<UsageMeter />);
    await userEvent.click(await screen.findByRole("button", { name: /CVs 8/ }));
    expect(within(screen.getByRole("dialog")).getByText("CVs 80% used")).toBeTruthy();
  });

  it("shows the worst warning beside the meter", async () => {
    stubServer({
      ...SUMMARY,
      cvs: { used: 10, limit: 10, left: 0, warning: 100 },
    });
    render(<UsageMeter />);
    expect(await screen.findByText("Limit reached")).toBeTruthy();
  });
});

describe("live updates", () => {
  it("reads again on the interval the server gives", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let used = 3;
    const fetchMock = stubServer(() => ({
      ...SUMMARY,
      cvs: { used, limit: 10, left: 10 - used, warning: null },
    }));
    render(<UsageMeter />);
    await screen.findByRole("button", { name: /CVs 3/ });
    used = 4;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(await screen.findByRole("button", { name: /CVs 4/ })).toBeTruthy();
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});

describe("who sees it", () => {
  it("is in the owner's top bar", async () => {
    stubServer();
    render(<CompanyTopBar companyName="Fake Co" userName="Fake Owner" role="owner" />);
    expect(await screen.findByRole("button", { name: /CVs 3/ })).toBeTruthy();
  });

  it("is not in a member's top bar and asks the server for nothing", () => {
    const fetchMock = stubServer();
    render(<CompanyTopBar companyName="Fake Co" userName="Fake Member" role="member" />);
    expect(screen.queryByRole("button", { name: /CVs/ })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
