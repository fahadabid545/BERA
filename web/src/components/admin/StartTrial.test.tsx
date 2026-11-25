import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminRole } from "./navigation";
import { AdminRoleProvider } from "./role";
import { StartTrial } from "./StartTrial";

const fetchMock = vi.fn();
const onStarted = vi.fn();

function reply(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

function show(role: AdminRole, state = "no_plan") {
  return render(
    <AdminRoleProvider value={role}>
      <StartTrial companyId="7" state={state} onStarted={onStarted} />
    </AdminRoleProvider>,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  onStarted.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === "POST") return reply({});
    return reply([{ id: 3, name: "Fake Starter", status: "active" }]);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("start a free trial", () => {
  it("is not shown to support", () => {
    show("support");
    expect(screen.queryByRole("button", { name: "Start free trial" })).toBeNull();
  });

  it("is not shown while the company has a plan", () => {
    show("super", "active");
    expect(screen.queryByRole("button", { name: "Start free trial" })).toBeNull();
  });

  it("sends the plan, days, CV limit and reason", async () => {
    const user = userEvent.setup();
    show("super");
    await user.click(screen.getByRole("button", { name: "Start free trial" }));
    const dialog = await screen.findByRole("dialog", { name: "Start free trial" });
    await user.type(within(dialog).getByLabelText("Days"), "14");
    await user.type(within(dialog).getByLabelText("CVs"), "50");
    await user.type(within(dialog).getByLabelText("Reason"), "Invited beta company");
    await user.click(within(dialog).getByRole("button", { name: "Start trial" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find((call) => call[1]?.method === "POST")!;
    expect(post[0]).toBe("/api/admin/companies/7/subscription/trial/");
    expect(JSON.parse(post[1].body)).toEqual({
      plan_id: 3,
      days: 14,
      cv_limit: 50,
      reason: "Invited beta company",
    });
  });

  it("shows the server's refusal", async () => {
    fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return reply(
          {
            error: {
              code: "trial_used",
              message: "A free trial is not available for your company.",
            },
          },
          409,
        );
      return reply([{ id: 3, name: "Fake Starter", status: "active" }]);
    });
    const user = userEvent.setup();
    show("super");
    await user.click(screen.getByRole("button", { name: "Start free trial" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Start trial" }),
    );
    expect(await screen.findByText("A free trial is not available for your company.")).toBeTruthy();
    expect(onStarted).not.toHaveBeenCalled();
  });
});
