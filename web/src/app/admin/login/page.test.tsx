import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FOOTER_LINKS, NAV_LINKS } from "@/components/website/links";

import AdminLoginPage from "./page";

describe("admin login page", () => {
  it("shows Email, Password and Log in, and no links", () => {
    const { container } = render(<AdminLoginPage />);
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Log in" })).toBeTruthy();
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });

  it("does nothing when Log in is pressed", async () => {
    const { container } = render(<AdminLoginPage />);
    const before = container.innerHTML;
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(container.innerHTML).toBe(before);
  });

  it("is not linked from the public website", () => {
    const websiteAddresses = [...NAV_LINKS, ...FOOTER_LINKS].map((link) => link.href);
    expect(websiteAddresses.some((address) => address.startsWith("/admin"))).toBe(false);
  });
});
