import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DataAndExport } from "./DataAndExport";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn();
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
const SETTINGS = {
  name: "Acme Ltd",
  country: "DE",
  retention: { days: 180, chosen: null, default_days: 180, choices: [30, 180] },
};
const subscription = (active: boolean) => ({
  subscription: { active, state: active ? "active" : "no_plan", period_end: null },
});
const posts = (path: string) =>
  fetchMock.mock.calls.filter((c) => c[1]?.method === "POST" && String(c[0]).includes(path));

function serve(active: boolean, extra: (path: string, init?: RequestInit) => unknown = () => null) {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    const special = extra(String(path), init);
    if (special) return special;
    if (String(path).includes("/settings/")) return reply(SETTINGS);
    if (String(path).includes("/deletion/")) {
      return init?.method === "POST"
        ? reply({ due_at: "2030-01-15T10:00:00Z" }, 202)
        : reply(subscription(active));
    }
    return reply({ id: "pkg1" }, 201);
  });
}
const openDelete = async () => {
  render(<DataAndExport />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Delete company" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete company" });
  await screen.findByLabelText('Type "Acme Ltd" to confirm');
  return { user, dialog };
};

beforeEach(() => {
  push.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("exporting data", () => {
  it("asks for the export and opens its download page", async () => {
    serve(false);
    render(<DataAndExport />);
    await userEvent.click(screen.getByRole("button", { name: "Export data" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company/downloads/pkg1"));
    expect(posts("/downloads/export/")).toHaveLength(1);
  });

  it("shows why it could not be made", async () => {
    serve(false, (path) =>
      path.includes("/export/")
        ? reply(
            { error: { code: "nothing_to_download", message: "There are no CVs to export." } },
            400,
          )
        : null,
    );
    render(<DataAndExport />);
    await userEvent.click(screen.getByRole("button", { name: "Export data" }));
    expect((await screen.findByRole("alert")).textContent).toBe("There are no CVs to export.");
    expect(push).not.toHaveBeenCalled();
  });
});

describe("deleting the company", () => {
  it("offers the export first inside the confirmation", async () => {
    serve(false);
    const { user, dialog } = await openDelete();
    await user.click(within(dialog).getByRole("button", { name: "Export data first" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company/downloads/pkg1"));
    expect(posts("/deletion/")).toHaveLength(0);
  });

  it("sends the typed name and shows the date it will be removed", async () => {
    serve(false);
    const { user, dialog } = await openDelete();
    await user.type(within(dialog).getByLabelText('Type "Acme Ltd" to confirm'), "Acme Ltd");
    await user.click(within(dialog).getByRole("button", { name: "Delete company" }));
    const done = await screen.findByRole("dialog", { name: "Company scheduled for deletion" });
    expect(within(done).getByText(/removed on 2030-01-15/)).toBeTruthy();
    expect(JSON.parse(posts("/deletion/")[0][1].body)).toEqual({
      confirm_name: "Acme Ltd",
      acknowledge_subscription: false,
    });
    await user.click(within(done).getByRole("button", { name: "Close" }));
    expect(push).toHaveBeenCalledWith("/login");
  });

  it("shows the server's message when the name is wrong", async () => {
    serve(false, (path, init) =>
      path.includes("/deletion/") && init?.method === "POST"
        ? reply(
            {
              error: {
                code: "invalid",
                message: "Check the form.",
                fields: { confirm_name: "Type the company name exactly to confirm." },
              },
            },
            400,
          )
        : null,
    );
    const { user, dialog } = await openDelete();
    await user.click(within(dialog).getByRole("button", { name: "Delete company" }));
    expect(await screen.findByText("Type the company name exactly to confirm.")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Company scheduled for deletion" })).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });

  it("warns about an active subscription and sends the acknowledgement", async () => {
    serve(true);
    const { user, dialog } = await openDelete();
    await user.click(within(dialog).getByLabelText("My active subscription ends with the company"));
    await user.type(within(dialog).getByLabelText('Type "Acme Ltd" to confirm'), "Acme Ltd");
    await user.click(within(dialog).getByRole("button", { name: "Delete company" }));
    await screen.findByRole("dialog", { name: "Company scheduled for deletion" });
    expect(JSON.parse(posts("/deletion/")[0][1].body).acknowledge_subscription).toBe(true);
  });

  it("does not mention a subscription when there is none", async () => {
    serve(false);
    const { dialog } = await openDelete();
    expect(
      within(dialog).queryByLabelText("My active subscription ends with the company"),
    ).toBeNull();
  });

  it("shows the server's refusal when the subscription was not acknowledged", async () => {
    serve(true, (path, init) =>
      path.includes("/deletion/") && init?.method === "POST"
        ? reply(
            {
              error: {
                code: "subscription_active",
                message: "Your company has an active subscription. Confirm to delete it anyway.",
              },
            },
            409,
          )
        : null,
    );
    const { user, dialog } = await openDelete();
    await user.type(within(dialog).getByLabelText('Type "Acme Ltd" to confirm'), "Acme Ltd");
    await user.click(within(dialog).getByRole("button", { name: "Delete company" }));
    expect((await screen.findByRole("alert")).textContent).toContain("active subscription");
  });
});
