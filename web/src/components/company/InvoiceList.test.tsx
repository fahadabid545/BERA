import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvoiceList } from "./InvoiceList";
import { RoleProvider } from "./role";

const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({ navigateTo: (address: string) => navigateTo(address) }));

const ROW = {
  id: "11111111-1111-1111-1111-111111111111",
  number: "INV-0001",
  issued_at: "2030-02-15T12:00:00Z",
  amount_minor: 1000,
  currency: "USD",
  plan_name: "Fake Plan",
  billed_to_name: "Fake Trading Ltd",
  can_download: true,
  can_view: true,
};

let invoices: object[];
let state: string;
let requested: string[];
let linkReply: () => Response;

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function show(role: "owner" | "member" = "owner") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      requested.push(path);
      if (path.includes("/link/")) return linkReply();
      if (path === "/api/company/usage/") return reply({ state });
      return reply({ invoices });
    }),
  );
  return render(
    <RoleProvider value={role}>
      <InvoiceList />
    </RoleProvider>,
  );
}

beforeEach(() => {
  invoices = [ROW];
  state = "active";
  requested = [];
  navigateTo.mockReset();
  linkReply = () => reply({ url: "https://invoice.example.test/pdf/1" });
});
afterEach(() => vi.unstubAllGlobals());

describe("invoices", () => {
  it("lists each invoice with its number, date, plan, name and amount", async () => {
    show();
    const row = (await screen.findByText("INV-0001")).closest("tr")!;
    expect(row.textContent).toContain("Feb 15, 2030");
    expect(row.textContent).toContain("Fake Plan");
    expect(row.textContent).toContain("Fake Trading Ltd");
    expect(row.textContent).toContain("USD 10.00");
  });

  it("downloads the PDF through the server, only when clicked", async () => {
    show();
    await screen.findByText("INV-0001");
    expect(requested.some((path) => path.includes("/link/"))).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Download invoice INV-0001" }));
    await waitFor(() =>
      expect(navigateTo).toHaveBeenCalledWith("https://invoice.example.test/pdf/1"),
    );
    expect(requested.at(-1)).toBe(`/api/company/billing/invoices/${ROW.id}/link/?kind=pdf`);
  });

  it("opens the hosted page the same way", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "View invoice INV-0001" }));
    await waitFor(() => expect(navigateTo).toHaveBeenCalled());
    expect(requested.at(-1)).toContain("kind=hosted");
  });

  it("turns a button off when the file is not ready", async () => {
    invoices = [{ ...ROW, can_download: false }];
    show();
    const button = await screen.findByRole("button", { name: "Download invoice INV-0001" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("says in plain words when a file cannot be opened", async () => {
    linkReply = () =>
      reply({ error: { code: "invoice_file_unavailable", message: "Not ready yet." } }, 409);
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Download invoice INV-0001" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not ready yet.");
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it("says plainly that there are no invoices yet", async () => {
    invoices = [];
    show();
    expect(await screen.findByText("No invoices yet.")).toBeTruthy();
  });

  it("says plainly that a free plan has no invoices", async () => {
    invoices = [];
    state = "granted_free";
    show();
    expect(await screen.findByText("A free plan has no invoices.")).toBeTruthy();
  });

  it("shows and asks for nothing when the person is not the owner", async () => {
    const { container } = show("member");
    await Promise.resolve();
    expect(container.textContent).toBe("");
    expect(requested).toEqual([]);
  });
});
