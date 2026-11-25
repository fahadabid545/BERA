import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type PublicPlan } from "@/components/website/PricingPlans";

import PricingPage from "./page";

const STARTER: PublicPlan = {
  id: 7,
  name: "Fake Starter",
  description: "For small teams",
  price: { currency: "USD", amount: "10.00", note: null, approximate: false },
  charged: { currency: "USD", amount: "10.00" },
  cvs_per_month: 250,
  cvs_per_project: 100,
  max_projects: 5,
  max_team_accounts: 3,
  max_top_n: 20,
};
const PAKISTAN: PublicPlan = {
  ...STARTER,
  id: 8,
  name: "Fake Growth",
  description: "",
  price: {
    currency: "PKR",
    amount: "5000.00",
    note: "Estimate only. You are charged in US dollars.",
    approximate: true,
  },
  charged: { currency: "USD", amount: "20.00" },
  cvs_per_month: 1500,
};

function show(
  plans: PublicPlan[] | "fails",
  status: unknown = { signed_in: false, can_pay: false },
) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      asked.push(path);
      if (path === "/api/auth/company/status/") {
        return status === "fails"
          ? new Response("{}", { status: 500 })
          : new Response(JSON.stringify(status));
      }
      return plans === "fails"
        ? new Response(
            JSON.stringify({ error: { code: "x", message: "We could not load plans." } }),
            {
              status: 500,
            },
          )
        : new Response(JSON.stringify(plans));
    }),
  );
  render(<PricingPage />);
  return asked;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the plans", () => {
  it("shows each plan from the server with its price and key limits", async () => {
    show([STARTER]);
    const card = await screen.findByLabelText("Fake Starter");
    expect(within(card).getByText("USD 10.00 per month")).toBeTruthy();
    expect(within(card).getByText("For small teams")).toBeTruthy();
    for (const line of [
      "250 CVs per month",
      "100 CVs per project",
      "Up to 5 projects",
      "Up to 3 team accounts",
      "Top 20 shortlist",
    ]) {
      expect(within(card).getByText(line)).toBeTruthy();
    }
  });

  it("shows a region price as an estimate next to what is charged, in the server's order", async () => {
    show([STARTER, PAKISTAN]);
    const second = await screen.findByLabelText("Fake Growth");
    expect(within(second).getByText("About PKR 5,000.00 per month")).toBeTruthy();
    expect(
      within(second).getByText(/Estimate only. You are charged in US dollars. Charged: USD 20.00/),
    ).toBeTruthy();
    expect(within(second).getByText("1,500 CVs per month")).toBeTruthy();
    const names = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(names).toEqual(["Fake Starter", "Fake Growth"]);
  });

  it("leaves out a limit the plan does not have, and an empty description", async () => {
    show([{ ...PAKISTAN, cvs_per_project: null, max_top_n: null }]);
    const card = await screen.findByLabelText("Fake Growth");
    expect(within(card).queryByText(/per project/)).toBeNull();
    expect(within(card).queryByText(/shortlist/)).toBeNull();
    expect(card.querySelectorAll("p")).toHaveLength(2);
  });

  it("shows a friendly message when there are no plans", async () => {
    show([]);
    expect((await screen.findByRole("status")).textContent).toBe(
      "No plans are available right now. Please check back soon.",
    );
    expect(screen.queryByRole("link", { name: "Choose plan" })).toBeNull();
  });

  it("shows the server's plain error when the plans cannot load", async () => {
    show("fails");
    expect((await screen.findByRole("alert")).textContent).toBe("We could not load plans.");
  });
});

describe("Choose plan", () => {
  it("goes to sign up for a visitor, one button for each plan", async () => {
    show([STARTER, PAKISTAN]);
    await screen.findByLabelText("Fake Starter");
    const links = screen.getAllByRole("link", { name: "Choose plan" });
    expect(links).toHaveLength(2);
    for (const link of links) expect(link.getAttribute("href")).toBe("/signup");
  });

  it("goes to billing for a signed-in owner", async () => {
    show([STARTER], { signed_in: true, can_pay: true });
    await screen.findByLabelText("Fake Starter");
    await vi.waitFor(() =>
      expect(screen.getByRole("link", { name: "Choose plan" }).getAttribute("href")).toBe(
        "/company/billing",
      ),
    );
  });

  it("sends a signed-in person who cannot pay to billing too, not to sign up", async () => {
    show([STARTER], { signed_in: true, can_pay: false });
    await screen.findByLabelText("Fake Starter");
    await vi.waitFor(() =>
      expect(screen.getByRole("link", { name: "Choose plan" }).getAttribute("href")).toBe(
        "/company/billing",
      ),
    );
  });

  it("falls back to sign up when the sign-in check fails", async () => {
    show([STARTER], "fails");
    await screen.findByLabelText("Fake Starter");
    expect(screen.getByRole("link", { name: "Choose plan" }).getAttribute("href")).toBe("/signup");
  });

  it("never puts a plan or a price in the link", async () => {
    show([STARTER, PAKISTAN], { signed_in: true, can_pay: true });
    await screen.findByLabelText("Fake Starter");
    await vi.waitFor(() =>
      expect(screen.getAllByRole("link", { name: "Choose plan" })[0].getAttribute("href")).toBe(
        "/company/billing",
      ),
    );
    for (const link of screen.getAllByRole("link", { name: "Choose plan" })) {
      expect(link.getAttribute("href")).not.toMatch(/[?#=]|7|8|10|20/);
    }
  });

  it("asks the server for the plans and for the sign-in status, nothing else", async () => {
    const asked = show([STARTER]);
    await screen.findByLabelText("Fake Starter");
    expect(asked.sort()).toEqual(["/api/auth/company/status/", "/api/plans/"]);
  });
});
