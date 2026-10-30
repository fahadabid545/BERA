import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui";

import { RenewalPrompt, UpgradePrompt } from "./BillingPrompt";

describe("UpgradePrompt", () => {
  const open = async () => {
    render(<UpgradePrompt trigger={<Button>Open</Button>} />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
  };

  it("is closed until opened, then shows Upgrade plan linking to Usage and Billing", async () => {
    render(<UpgradePrompt trigger={<Button>Open</Button>} />);
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
    render(<RenewalPrompt trigger={<Button>Open</Button>} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("link", { name: "Renew subscription" }).getAttribute("href")).toBe(
      "/company/billing",
    );
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
