import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UserMenu } from "./UserMenu";

const logOut = vi.fn();
vi.mock("@/lib/logout", () => ({ logOut: () => logOut() }));

describe("the user menu", () => {
  it("lists the given links and then Log out", async () => {
    render(<UserMenu userName="Fake Person" items={[{ label: "Profile", href: "/profile" }]} />);
    await userEvent.click(screen.getByRole("button", { name: "User menu" }));
    const items = screen.getAllByRole("menuitem").map((item) => item.textContent);
    expect(items).toEqual(["Profile", "Log out"]);
  });

  it("ends the session when Log out is chosen", async () => {
    render(<UserMenu userName="Fake Person" items={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "User menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Log out" }));
    expect(logOut).toHaveBeenCalledTimes(1);
  });
});
