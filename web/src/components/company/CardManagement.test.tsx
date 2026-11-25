import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CardManagement } from "./CardManagement";

const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({ navigateTo: (address: string) => navigateTo(address) }));

const VISA = { brand: "visa", last4: "4242", exp_month: 4, exp_year: 2030 };
let card: object | null;
let checks: string[];
let posted: string[];
let openReply: () => Response;
const onResult = vi.fn();

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function show(returned = false) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push(path);
        if (path.endsWith("/check/")) return reply({ result: checks.shift() ?? "checking" });
        return openReply();
      }
      return reply({ card });
    }),
  );
  return render(<CardManagement returned={returned} refreshSeconds={0} onResult={onResult} />);
}

beforeEach(() => {
  card = VISA;
  checks = [];
  posted = [];
  onResult.mockReset();
  navigateTo.mockReset();
  openReply = () => reply({ url: "https://billing.example.test/card" });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the card on file", () => {
  it("shows the brand, last four digits and expiry", async () => {
    show();
    expect(await screen.findByText("Visa ending 4242, expires 04/2030")).toBeTruthy();
  });

  it("says plainly when there is no card", async () => {
    card = null;
    show();
    expect(await screen.findByText("No card on file")).toBeTruthy();
  });
});

describe("updating it", () => {
  it("sends the owner to the provider's page", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Update card" }));
    await waitFor(() =>
      expect(navigateTo).toHaveBeenCalledWith("https://billing.example.test/card"),
    );
    expect(posted).toEqual(["/api/company/billing/card/update/"]);
  });

  it("shows a refusal in plain words and stays", async () => {
    openReply = () => reply({ error: { code: "x", message: "We could not reach it." } }, 502);
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Update card" }));
    expect((await screen.findByRole("alert")).textContent).toBe("We could not reach it.");
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it("asks the server nothing about a result when the owner did not just come back", async () => {
    show();
    await screen.findByText("Visa ending 4242, expires 04/2030");
    expect(posted).toEqual([]);
  });
});

describe("coming back", () => {
  it("shows Card updated from the server's answer, and reads the card again", async () => {
    checks = ["updated"];
    show(true);
    expect(await screen.findByText("Card updated")).toBeTruthy();
    expect(onResult).toHaveBeenCalledWith("updated");
  });

  it("shows Not changed", async () => {
    checks = ["not_changed"];
    show(true);
    expect(await screen.findByText("Not changed")).toBeTruthy();
    expect(onResult).toHaveBeenCalledWith("not_changed");
  });

  it("shows Checking your card and asks again until it can tell", async () => {
    checks = ["checking", "checking", "updated"];
    show(true);
    expect(await screen.findByText("Card updated")).toBeTruthy();
    expect(posted.filter((path) => path.endsWith("/check/"))).toHaveLength(3);
  });

  it("stops asking once it has an answer", async () => {
    checks = ["not_changed"];
    show(true);
    await screen.findByText("Not changed");
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(posted.filter((path) => path.endsWith("/check/"))).toHaveLength(1);
  });
});
