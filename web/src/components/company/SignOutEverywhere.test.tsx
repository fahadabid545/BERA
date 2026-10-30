import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignOutEverywhere } from "./SignOutEverywhere";

const logOutEverywhere = vi.fn();
vi.mock("@/lib/logout", () => ({ logOutEverywhere: () => logOutEverywhere() }));

beforeEach(() => logOutEverywhere.mockClear());

describe("sign out of all devices", () => {
  it("asks first, in a popup", async () => {
    render(<SignOutEverywhere />);
    await userEvent.click(screen.getByRole("button", { name: "Sign out of all devices" }));
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByRole("button", { name: "Cancel" })).toBeTruthy();
    expect(logOutEverywhere).not.toHaveBeenCalled();
  });

  it("does nothing when cancelled", async () => {
    render(<SignOutEverywhere />);
    await userEvent.click(screen.getByRole("button", { name: "Sign out of all devices" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(logOutEverywhere).not.toHaveBeenCalled();
  });

  it("signs out everywhere when confirmed", async () => {
    render(<SignOutEverywhere />);
    await userEvent.click(screen.getByRole("button", { name: "Sign out of all devices" }));
    const popup = await screen.findByRole("dialog");
    await userEvent.click(within(popup).getByRole("button", { name: "Sign out of all devices" }));
    expect(logOutEverywhere).toHaveBeenCalledTimes(1);
  });
});
