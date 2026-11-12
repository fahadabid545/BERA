import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FOOTER_LINKS, NAV_LINKS } from "@/components/website/links";

import AdminLoginPage from "./page";

vi.mock("qrcode", () => ({ default: { toDataURL: async () => "data:image/png;base64,AAAA" } }));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

type Reply = { status?: number; body: unknown };

/** Answers each address with the next reply queued for it, and remembers every call. */
function stubServer(replies: Record<string, Reply>) {
  const fetchMock = vi.fn(async (path: string) => {
    const reply = replies[path];
    if (!reply) throw new TypeError("no reply for " + path);
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function logIn() {
  await userEvent.type(screen.getByLabelText("Email"), "boss@example.test");
  await userEvent.type(screen.getByLabelText("Password"), "the-right-password-1");
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
}

function bodyOf(server: ReturnType<typeof stubServer>, path: string) {
  const call = server.mock.calls.find((entry) => entry[0] === path) as unknown as
    [string, RequestInit] | undefined;
  return JSON.parse(String(call?.[1].body));
}

beforeEach(() => push.mockClear());
afterEach(() => vi.unstubAllGlobals());

describe("admin login page", () => {
  it("shows Email, Password and Log in, and no links", () => {
    const { container } = render(<AdminLoginPage />);
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Log in" })).toBeTruthy();
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });

  it("asks for the authenticator code after the password and then opens the admin panel", async () => {
    const server = stubServer({
      "/api/auth/admin/login/": { body: { status: "two_step_required", challenge: "signed" } },
      "/api/auth/admin/login/two-step/": { body: { status: "ok" } },
    });
    render(<AdminLoginPage />);
    await logIn();
    expect(push).not.toHaveBeenCalled(); // the password alone does not sign in
    await userEvent.type(await screen.findByLabelText("Code from your app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/admin"));
    expect(bodyOf(server, "/api/auth/admin/login/two-step/")).toEqual({
      challenge: "signed",
      code: "123456",
    });
  });

  it("offers no recovery code and no support link for an admin", async () => {
    stubServer({
      "/api/auth/admin/login/": { body: { status: "two_step_required", challenge: "signed" } },
    });
    const { container } = render(<AdminLoginPage />);
    await logIn();
    await screen.findByLabelText("Code from your app");
    expect(screen.queryByRole("button", { name: /recovery code/i })).toBeNull();
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });

  it("shows that another super admin resets a lost device when the code is wrong", async () => {
    const message =
      "That code is not correct. If you lost your device, another super admin must reset it.";
    stubServer({
      "/api/auth/admin/login/": { body: { status: "two_step_required", challenge: "signed" } },
      "/api/auth/admin/login/two-step/": {
        status: 400,
        body: { error: { code: "two_step_code_wrong", message, fields: { code: message } } },
      },
    });
    render(<AdminLoginPage />);
    await logIn();
    await userEvent.type(await screen.findByLabelText("Code from your app"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText(message)).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  it("sets the authenticator up first when the admin has none, then signs in without recovery codes", async () => {
    const server = stubServer({
      "/api/auth/admin/login/": {
        body: { status: "two_step_setup_required", challenge: "signed" },
      },
      "/api/auth/admin/login/two-step/setup/": {
        body: { secret: "ABCDEFGH", uri: "otpauth://totp/Bera:boss?secret=ABCDEFGH" },
      },
      "/api/auth/admin/login/two-step/setup/confirm/": {
        body: { status: "ok", recovery_codes: [] },
      },
    });
    render(<AdminLoginPage />);
    await logIn();
    await userEvent.type(await screen.findByLabelText("Code from your app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/admin"));
    expect(screen.queryByText("Recovery codes")).toBeNull();
    expect(bodyOf(server, "/api/auth/admin/login/two-step/setup/confirm/")).toEqual({
      challenge: "signed",
      code: "123456",
    });
  });

  it("shows a wrong password in plain words and stays on the form", async () => {
    stubServer({
      "/api/auth/admin/login/": {
        status: 400,
        body: {
          error: { code: "invalid_credentials", message: "Email or password is incorrect." },
        },
      },
    });
    render(<AdminLoginPage />);
    await logIn();
    expect(await screen.findByText("Email or password is incorrect.")).toBeTruthy();
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  it("is not linked from the public website", () => {
    const websiteAddresses = [...NAV_LINKS, ...FOOTER_LINKS].map((link) => link.href);
    expect(websiteAddresses.some((address) => address.startsWith("/admin"))).toBe(false);
  });
});
