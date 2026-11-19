import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui";

import { HighestPlanPrompt, RenewalPrompt, UpgradePrompt } from "./BillingPrompt";
import { RoleProvider } from "./role";

describe("UpgradePrompt", () => {
  const open = async () => {
    render(
      <RoleProvider value="owner">
        <UpgradePrompt trigger={<Button>Open</Button>} />
      </RoleProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
  };

  it("is closed until opened, then shows Upgrade plan linking to Usage and Billing", async () => {
    render(
      <RoleProvider value="owner">
        <UpgradePrompt trigger={<Button>Open</Button>} />
      </RoleProvider>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Upgrade plan" }).getAttribute("href")).toBe(
      "/company/billing",
    );
  });

  it("closes with Close and with Escape", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("RenewalPrompt", () => {
  it("shows Renew subscription linking to Usage and Billing, and closes", async () => {
    render(
      <RoleProvider value="owner">
        <RenewalPrompt trigger={<Button>Open</Button>} />
      </RoleProvider>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("link", { name: "Renew subscription" }).getAttribute("href")).toBe(
      "/company/billing",
    );
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("HighestPlanPrompt", () => {
  it("offers Contact us to an owner", async () => {
    render(
      <RoleProvider value="owner">
        <HighestPlanPrompt trigger={<Button>Open</Button>} />
      </RoleProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByText("You have used your highest plan")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Contact us" }).getAttribute("href")).toBe("/contact");
  });
});

describe("a member", () => {
  it.each([
    ["upgrade", UpgradePrompt, "Please ask your company owner to upgrade.", "Upgrade plan"],
    ["renewal", RenewalPrompt, "Please ask your company owner to renew.", "Renew subscription"],
    [
      "highest plan",
      HighestPlanPrompt,
      "Please ask your company owner to get in touch.",
      "Contact us",
    ],
  ])("sees the %s popup without its button", async (_name, Prompt, words, button) => {
    render(
      <RoleProvider value="member">
        <Prompt trigger={<Button>Open</Button>} />
      </RoleProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByText(words)).toBeTruthy();
    expect(screen.queryByRole("link", { name: button })).toBeNull();
  });

  it("is the default when nobody says the role", async () => {
    render(<UpgradePrompt trigger={<Button>Open</Button>} />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.queryByRole("link", { name: "Upgrade plan" })).toBeNull();
  });
});
