import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SignUpPage from "./page";

const HINTS = {
  rules: [{ id: "min_length", text: "At least 12 characters", met: true }],
  ok: true,
};
const NEUTRAL = "If this email can be used, we have sent instructions.";

type Reply = { status?: number; body: unknown };

/** Pretends to be the server: one answer for the country lookup, one for the sign-up. */
function stubServer({ country, signUp }: { country?: Reply; signUp?: Reply }) {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith("/password-check/"))
      return new Response(JSON.stringify(HINTS), { status: 200 });
    const reply = path.endsWith("/country/")
      ? (country ?? { body: { country: "ZZ" } })
      : (signUp ?? { body: {} });
    if (reply.body === "network-down") throw new TypeError("network down");
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function signUpCalls(fetchMock: ReturnType<typeof stubServer>) {
  return fetchMock.mock.calls.filter(
    ([path]) => !String(path).endsWith("/country/") && !String(path).endsWith("/password-check/"),
  );
}

async function fillIn(overrides: Partial<Record<string, string>> = {}) {
  const values = {
    "Company name": "Fake Test Ltd",
    "Your name": "Fake Owner",
    Email: "owner@example.test",
    Password: "violet-harbour-lantern-92", // nosecret: fake test value
    ...overrides,
  };
  for (const [label, value] of Object.entries(values)) {
    await userEvent.type(screen.getByLabelText(label), value as string);
  }
}

beforeEach(() => {
  stubServer({});
});
afterEach(() => vi.unstubAllGlobals());

describe("sign up page", () => {
  it("shows every labelled field and the Create account button", () => {
    render(<SignUpPage />);
    for (const label of ["Company name", "Your name", "Email", "Password", "Country"]) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Create account" })).toBeTruthy();
  });

  it("has the acceptance checkbox with Terms and Privacy Policy linking to their pages", () => {
    render(<SignUpPage />);
    expect(
      screen.getByRole("checkbox", { name: /I accept the Terms and Privacy Policy/ }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Terms" }).getAttribute("href")).toBe("/terms");
    expect(screen.getByRole("link", { name: "Privacy Policy" }).getAttribute("href")).toBe(
      "/privacy",
    );
  });

  it("links back to Log in", () => {
    render(<SignUpPage />);
    expect(
      screen.getByRole("link", { name: "Already have an account? Log in" }).getAttribute("href"),
    ).toBe("/login");
  });
});

describe("the country", () => {
  const countrySelect = () => screen.getByLabelText("Country") as HTMLSelectElement;

  it("shows the detected country, so it can be changed before submitting", async () => {
    stubServer({ country: { body: { country: "PK" } } });
    render(<SignUpPage />);
    await waitFor(() => expect(countrySelect().value).toBe("PK"));
    expect(within(countrySelect()).getByRole("option", { name: "Pakistan" })).toBeTruthy();
  });

  it("starts at Other when the country cannot be detected", async () => {
    stubServer({ country: { body: { country: "ZZ" } } });
    render(<SignUpPage />);
    await waitFor(() => expect(countrySelect().selectedOptions[0].textContent).toBe("Other"));
  });

  it("stays at Other when the lookup fails", async () => {
    stubServer({ country: { body: "network-down" } });
    render(<SignUpPage />);
    await waitFor(() => expect(countrySelect().value).toBe("ZZ"));
  });

  it("ignores an answer that is not a country code", async () => {
    stubServer({ country: { body: { country: "<script>" } } });
    render(<SignUpPage />);
    await waitFor(() => expect(countrySelect().value).toBe("ZZ"));
  });

  it("does not overwrite a country the visitor already chose", async () => {
    let answer: (reply: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => (answer = resolve))),
    );
    render(<SignUpPage />);
    await userEvent.selectOptions(countrySelect(), "DE");
    answer(new Response(JSON.stringify({ country: "PK" })));
    await waitFor(() => expect(countrySelect().value).toBe("DE"));
  });

  it("lists Other last", () => {
    render(<SignUpPage />);
    const options = within(countrySelect()).getAllByRole("option");
    expect(options.at(-1)?.textContent).toBe("Other");
    expect(options.length).toBeGreaterThan(240);
  });
});

describe("submitting", () => {
  it("sends the fields and the chosen country to the server", async () => {
    const server = stubServer({ country: { body: { country: "PK" } } });
    render(<SignUpPage />);
    await fillIn();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(signUpCalls(server)).toHaveLength(1));
    const [path, init] = signUpCalls(server)[0];
    expect(path).toBe("/api/auth/company/signup/");
    expect(JSON.parse(String(init?.body))).toEqual({
      company_name: "Fake Test Ltd",
      name: "Fake Owner",
      email: "owner@example.test",
      password: "violet-harbour-lantern-92", // nosecret: fake test value
      country: "PK",
      accept_terms: true,
    });
  });

  it("sends accept_terms as false when the box is not ticked", async () => {
    const server = stubServer({});
    render(<SignUpPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(signUpCalls(server)).toHaveLength(1));
    expect(JSON.parse(String(signUpCalls(server)[0][1]?.body)).accept_terms).toBe(false);
  });

  it("shows the neutral message in a popup after a successful sign up", async () => {
    stubServer({ signUp: { body: { status: "ok", message: NEUTRAL } } });
    render(<SignUpPage />);
    await fillIn();
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText(NEUTRAL)).toBeTruthy();
    expect(within(popup).getByRole("link", { name: "Log in" }).getAttribute("href")).toBe("/login");
    await userEvent.click(within(popup).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows why a weak password was refused, next to the password", async () => {
    stubServer({
      signUp: {
        status: 400,
        body: {
          error: {
            code: "validation_error",
            message: "Please check the form and try again.",
            fields: { password: "Use at least 12 characters. This password is too common." },
          },
        },
      },
    });
    render(<SignUpPage />);
    await fillIn({ Password: "password" });
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    const password = screen.getByLabelText("Password");
    await waitFor(() => expect(password.getAttribute("aria-invalid")).toBe("true"));
    expect(
      screen.getByText(/Use at least 12 characters\. This password is too common\./),
    ).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows the message about the terms when they are not ticked", async () => {
    stubServer({
      signUp: {
        status: 400,
        body: {
          error: {
            code: "validation_error",
            message: "x",
            fields: { accept_terms: "Accept the Terms and Privacy Policy to continue." },
          },
        },
      },
    });
    render(<SignUpPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(
      await screen.findByText("Accept the Terms and Privacy Policy to continue."),
    ).toBeTruthy();
  });

  it("tells the visitor to wait when sign ups are slowed down", async () => {
    stubServer({
      signUp: {
        status: 429,
        body: {
          error: {
            code: "too_many_requests",
            message: "Too many attempts. Try again in 12 minutes.",
          },
        },
      },
    });
    render(<SignUpPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Too many attempts. Try again in 12 minutes.",
    );
  });

  it("says so in words when the server cannot be reached", async () => {
    stubServer({ signUp: { body: "network-down" } });
    render(<SignUpPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not reach the server/);
  });

  it("keeps what was typed after a refusal", async () => {
    stubServer({
      signUp: {
        status: 400,
        body: { error: { code: "validation_error", message: "x", fields: { password: "no" } } },
      },
    });
    render(<SignUpPage />);
    await fillIn();
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await screen.findByText("no");
    expect((screen.getByLabelText("Company name") as HTMLInputElement).value).toBe("Fake Test Ltd");
  });

  it("cannot be pressed again while waiting for the server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    render(<SignUpPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "Create account" }) as HTMLButtonElement).disabled,
      ).toBe(true),
    );
  });
});
