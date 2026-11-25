import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ContactPage from "./page";

const NOTE = "We use your name and email only to reply. We keep your message for 90 days.";
let posted: Record<string, unknown>[];
let sendReply: () => Response;
let formReply: () => Response;
let formCalls: number;

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  posted = [];
  formCalls = 0;
  formReply = () =>
    reply({ privacy_note: NOTE, form_token: `token-${formCalls}`, refresh_after_seconds: 3000 });
  sendReply = () => reply({ message: "Thank you. Your message was sent." });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push(JSON.parse(String(init.body)));
        return sendReply();
      }
      formCalls += 1;
      return formReply();
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function fillIn() {
  await userEvent.type(screen.getByLabelText("Name"), "Fake Person");
  await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
  await userEvent.type(screen.getByLabelText("Message"), "Hello");
}

describe("contact page", () => {
  it("shows labelled Name, Email and Message fields and a Send button", async () => {
    render(<ContactPage />);
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    expect(screen.getByLabelText("Message").tagName).toBe("TEXTAREA");
    expect(await screen.findByRole("button", { name: "Send" })).toBeTruthy();
  });

  it("shows the privacy notice from the server with a link to the Privacy page", async () => {
    render(<ContactPage />);
    expect(await screen.findByText(/We keep your message for 90 days\./)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Privacy page" }).getAttribute("href")).toBe(
      "/privacy",
    );
  });

  it("sends the message with the signed token and thanks the sender", async () => {
    render(<ContactPage />);
    await screen.findByText(/90 days/);
    await fillIn();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Thank you. Your message was sent.")).toBeTruthy();
    expect(posted).toEqual([
      {
        name: "Fake Person",
        email: "user@example.com",
        message: "Hello",
        website: "",
        form_token: "token-1",
      },
    ]);
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("");
  });

  it("asks for a fresh token after sending", async () => {
    render(<ContactPage />);
    await screen.findByText(/90 days/);
    await fillIn();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(formCalls).toBe(2));
  });

  it("hides the spam trap from people and screen readers", async () => {
    const { container } = render(<ContactPage />);
    await screen.findByText(/90 days/);
    const trap = container.querySelector('input[name="website"]') as HTMLInputElement;
    expect(trap.tabIndex).toBe(-1);
    expect(trap.autocomplete).toBe("off");
    expect(trap.closest("[aria-hidden='true']")).toBeTruthy();
    expect(screen.queryByLabelText("website")).toBeNull();
  });

  it("shows each mistake beside its field and keeps what was typed", async () => {
    sendReply = () =>
      reply(
        {
          error: {
            code: "invalid",
            message: "Check the form.",
            fields: { email: "Enter a valid email." },
          },
        },
        400,
      );
    render(<ContactPage />);
    await screen.findByText(/90 days/);
    await fillIn();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/Enter a valid email\./)).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Fake Person");
    expect(screen.queryByText("Thank you. Your message was sent.")).toBeNull();
  });

  it("shows a clear message when the limit is reached", async () => {
    sendReply = () =>
      reply(
        { error: { code: "rate_limited", message: "Too many requests. Try again later." } },
        429,
      );
    render(<ContactPage />);
    await screen.findByText(/90 days/);
    await fillIn();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Too many requests. Try again later.",
    );
  });

  it("shows a clear message when sending failed and lets the sender try again", async () => {
    sendReply = () =>
      reply(
        { error: { code: "contact_not_sent", message: "We could not send your message." } },
        503,
      );
    render(<ContactPage />);
    await screen.findByText(/90 days/);
    await fillIn();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect((await screen.findByRole("alert")).textContent).toBe("We could not send your message.");
    sendReply = () => reply({ message: "Thank you. Your message was sent." });
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Thank you. Your message was sent.")).toBeTruthy();
  });

  it("cannot send, and says why, when the form could not be loaded", async () => {
    formReply = () => reply({ error: { code: "x", message: "Something went wrong." } }, 500);
    render(<ContactPage />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
    expect(posted).toEqual([]);
  });

  it("asks for a fresh token before the old one expires", async () => {
    formReply = () => reply({ privacy_note: NOTE, form_token: "t", refresh_after_seconds: 0 });
    render(<ContactPage />);
    await waitFor(() => expect(formCalls).toBeGreaterThan(1));
  });
});
