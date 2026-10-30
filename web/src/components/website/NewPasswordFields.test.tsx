import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NewPasswordFields } from "./NewPasswordFields";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ rules: [], ok: false }), { status: 200 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

const WITH_CONFIRM = (
  <NewPasswordFields
    passwordLabel="New password"
    passwordName="password"
    confirm={{ label: "Confirm password", name: "confirm_password" }}
  />
);

describe("new password fields", () => {
  it("has a password field, and a confirm field only when asked for", () => {
    const { unmount } = render(
      <NewPasswordFields passwordLabel="Password" passwordName="password" />,
    );
    expect(screen.getByLabelText("Password")).toBeTruthy();
    expect(screen.queryByLabelText("Confirm password")).toBeNull();
    unmount();
    render(WITH_CONFIRM);
    expect((screen.getByLabelText("Confirm password") as HTMLInputElement).type).toBe("password");
  });

  it("says nothing about matching until the confirm field is used", () => {
    render(WITH_CONFIRM);
    expect(screen.queryByText(/passwords (do not )?match/)).toBeNull();
  });

  it("says live whether the two entries match", async () => {
    render(WITH_CONFIRM);
    await userEvent.type(screen.getByLabelText("New password"), "abcdef");
    await userEvent.type(screen.getByLabelText("Confirm password"), "abcdeX");
    expect(screen.getByRole("status").textContent).toBe("The passwords do not match.");
    await userEvent.clear(screen.getByLabelText("Confirm password"));
    await userEvent.type(screen.getByLabelText("Confirm password"), "abcdef");
    expect(screen.getByRole("status").textContent).toBe("The passwords match.");
  });

  it("notices when the first entry changes after the second was typed", async () => {
    render(WITH_CONFIRM);
    await userEvent.type(screen.getByLabelText("New password"), "abc");
    await userEvent.type(screen.getByLabelText("Confirm password"), "abc");
    await userEvent.type(screen.getByLabelText("New password"), "d");
    expect(screen.getByRole("status").textContent).toBe("The passwords do not match.");
  });

  it("shows errors from the server next to the fields", () => {
    render(
      <NewPasswordFields
        passwordLabel="New password"
        passwordName="password"
        passwordError="Use at least 12 characters."
        confirm={{ label: "Confirm password", name: "c", error: "The passwords do not match." }}
      />,
    );
    expect(screen.getByLabelText("New password").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Confirm password").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getAllByText("The passwords do not match.")).toHaveLength(1);
  });
});
