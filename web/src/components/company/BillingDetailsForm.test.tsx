import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BillingDetailsForm } from "./BillingDetailsForm";
import { RoleProvider } from "./role";

const SAVED = {
  name: "Fake Trading Ltd",
  address_line1: "1 Fake Street",
  address_line2: "",
  city: "Faketown",
  state: "",
  postal_code: "FK1 2AB",
  country: "GB",
  tax_number: "TAX-123",
  complete: true,
};
const EMPTY = {
  name: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  postal_code: "",
  country: "",
  tax_number: "",
  complete: false,
};

let current: object;
let putReply: () => Response;
let puts: unknown[];
let gets: number;

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function show(role: "owner" | "member" = "owner") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        puts.push(JSON.parse(String(init.body)));
        return putReply();
      }
      gets += 1;
      return reply(current);
    }),
  );
  return render(
    <RoleProvider value={role}>
      <BillingDetailsForm />
    </RoleProvider>,
  );
}

beforeEach(() => {
  current = SAVED;
  puts = [];
  gets = 0;
  putReply = () => reply(SAVED);
});
afterEach(() => vi.unstubAllGlobals());

describe("billing details", () => {
  it("shows the saved details to the owner, the tax number included", async () => {
    show();
    expect(((await screen.findByLabelText("Billing name")) as HTMLInputElement).value).toBe(
      "Fake Trading Ltd",
    );
    expect((screen.getByLabelText("Tax number (optional)") as HTMLInputElement).value).toBe(
      "TAX-123",
    );
    expect((screen.getByLabelText("Billing country") as HTMLSelectElement).value).toBe("GB");
  });

  it("shows and asks for nothing when the person is not the owner", async () => {
    const { container } = show("member");
    await Promise.resolve();
    expect(container.textContent).toBe("");
    expect(gets).toBe(0);
  });

  it("offers only real countries, and not Other", async () => {
    show();
    const select = (await screen.findByLabelText("Billing country")) as HTMLSelectElement;
    const labels = Array.from(select.options).map((option) => option.textContent);
    expect(labels).toContain("Pakistan");
    expect(labels).not.toContain("Other");
  });

  it("keeps Save off until something changed", async () => {
    show();
    const save = await screen.findByRole("button", { name: "Save" });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText("City"), "x");
    expect((save as HTMLButtonElement).disabled).toBe(false);
  });

  it("asks for confirmation, then saves every field", async () => {
    show();
    await userEvent.clear(await screen.findByLabelText("City"));
    await userEvent.type(screen.getByLabelText("City"), "Newtown");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(puts).toHaveLength(0);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({
      ...SAVED,
      city: "Newtown",
      complete: undefined,
    });
    expect(await screen.findByText("Billing details saved")).toBeTruthy();
  });

  it("shows what is missing next to the field", async () => {
    current = EMPTY;
    putReply = () =>
      reply(
        {
          error: {
            code: "validation_error",
            message: "Please check the form.",
            fields: { name: "This field is required.", country: "Choose a country." },
          },
        },
        400,
      );
    show();
    await userEvent.type(await screen.findByLabelText("Tax number (optional)"), "A1");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("This field is required.")).toBeTruthy();
    expect(screen.getByText("Choose a country.")).toBeTruthy();
  });

  it("says in plain words when saving failed for another reason", async () => {
    putReply = () =>
      reply({ error: { code: "payment_provider_error", message: "Try later." } }, 502);
    show();
    await userEvent.type(await screen.findByLabelText("City"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Try later.");
  });
});
