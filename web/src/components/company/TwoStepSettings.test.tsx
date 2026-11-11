import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TwoStepSettings } from "./TwoStepSettings";

vi.mock("qrcode", () => ({ default: { toDataURL: async () => "data:image/png;base64,AAAA" } }));

type Status = { enabled: boolean; recovery_codes_left: number; required_by_company: boolean };
const OFF: Status = { enabled: false, recovery_codes_left: 0, required_by_company: false };
const ON: Status = { enabled: true, recovery_codes_left: 8, required_by_company: false };

function stubServer(
  status: Status,
  replies: Record<string, { status?: number; body: unknown }> = {},
) {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    const reply = replies[`${init?.method ?? "GET"} ${path}`];
    if (reply) return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
    return new Response(JSON.stringify(status));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const callsTo = (server: ReturnType<typeof stubServer>, method: string, suffix: string) =>
  server.mock.calls.filter(
    ([path, init]) => String(path).endsWith(suffix) && (init?.method ?? "GET") === method,
  );

afterEach(() => vi.unstubAllGlobals());

describe("two-step settings", () => {
  it("offers setup while it is off", async () => {
    stubServer(OFF);
    render(<TwoStepSettings />);
    expect(
      await screen.findByRole("button", { name: "Set up two-step verification" }),
    ).toBeTruthy();
    expect(screen.queryByText(/Recovery codes left/)).toBeNull();
  });

  it("walks through setup and shows the recovery codes once", async () => {
    const codes = ["AAAAA-BBBBB", "CCCCC-DDDDD"];
    const server = stubServer(OFF, {
      "POST /api/auth/company/two-step/setup/": {
        body: { secret: "ABCDEFGH", uri: "otpauth://totp/Bera:x?secret=ABCDEFGH" },
      },
      "POST /api/auth/company/two-step/setup/confirm/": { body: { recovery_codes: codes } },
    });
    render(<TwoStepSettings />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Set up two-step verification" }),
    );

    expect(await screen.findByAltText("QR code for your authenticator app")).toBeTruthy();
    expect(screen.getByText("ABCDEFGH")).toBeTruthy();
    await userEvent.type(screen.getByLabelText("Code from your app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));

    const list = await screen.findByRole("list", { name: "Recovery codes" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(codes);
    expect(JSON.parse(String(callsTo(server, "POST", "/setup/confirm/")[0][1]?.body))).toEqual({
      code: "123456",
    });
    await userEvent.click(screen.getByRole("button", { name: "I have saved my codes" }));
    await waitFor(() => expect(callsTo(server, "GET", "/two-step/").length).toBeGreaterThan(1));
  });

  it("says plainly when the code was wrong and stays on the setup", async () => {
    stubServer(OFF, {
      "POST /api/auth/company/two-step/setup/": {
        body: { secret: "ABCDEFGH", uri: "otpauth://x" },
      },
      "POST /api/auth/company/two-step/setup/confirm/": {
        status: 400,
        body: {
          error: {
            code: "two_step_code_wrong",
            message: "That code is not correct. Try again.",
            fields: { code: "That code is not correct. Try again." },
          },
        },
      },
    });
    render(<TwoStepSettings />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Set up two-step verification" }),
    );
    await screen.findByAltText("QR code for your authenticator app");
    await userEvent.type(screen.getByLabelText("Code from your app"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));
    expect(await screen.findByText("That code is not correct. Try again.")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Recovery codes" })).toBeNull();
  });

  it("shows how many recovery codes are left while it is on", async () => {
    stubServer(ON);
    render(<TwoStepSettings />);
    expect(await screen.findByText(/Recovery codes left: 8/)).toBeTruthy();
  });

  it("turns it off only after the password and a code and a confirmation", async () => {
    const server = stubServer(ON, {
      "POST /api/auth/company/two-step/turn-off/": { body: { status: "ok" } },
    });
    render(<TwoStepSettings />);
    await userEvent.type(await screen.findByLabelText("Password"), "the-password-1");
    await userEvent.type(screen.getByLabelText("Code from your app or a recovery code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn off two-step verification" }));

    expect(callsTo(server, "POST", "/turn-off/")).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(callsTo(server, "POST", "/turn-off/")).toHaveLength(1));
    expect(JSON.parse(String(callsTo(server, "POST", "/turn-off/")[0][1]?.body))).toEqual({
      password: "the-password-1",
      code: "123456",
    });
  });

  it("shows the refusal when turning it off fails", async () => {
    stubServer(ON, {
      "POST /api/auth/company/two-step/turn-off/": {
        status: 400,
        body: {
          error: {
            code: "wrong_current_password",
            message: "Your password is incorrect.",
            fields: { password: "Your password is incorrect." },
          },
        },
      },
    });
    render(<TwoStepSettings />);
    await userEvent.type(await screen.findByLabelText("Password"), "wrong");
    await userEvent.type(screen.getByLabelText("Code from your app or a recovery code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn off two-step verification" }));
    await userEvent.click(await screen.findByRole("button", { name: "Turn off" }));
    expect(await screen.findByText("Your password is incorrect.")).toBeTruthy();
  });

  it("requires it for members only after a confirmation", async () => {
    const server = stubServer(OFF, {
      "PUT /api/auth/company/two-step/company-requirement/": { body: { required: true } },
    });
    render(<TwoStepSettings />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Require it for all members" }),
    );
    expect(callsTo(server, "PUT", "/company-requirement/")).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: "Require it" }));
    await waitFor(() => expect(callsTo(server, "PUT", "/company-requirement/")).toHaveLength(1));
    expect(JSON.parse(String(callsTo(server, "PUT", "/company-requirement/")[0][1]?.body))).toEqual(
      {
        required: true,
      },
    );
  });

  it("offers to stop requiring it when it is required", async () => {
    stubServer({ ...OFF, required_by_company: true });
    render(<TwoStepSettings />);
    expect(
      await screen.findByRole("button", { name: "Stop requiring it for members" }),
    ).toBeTruthy();
  });

  it("starts the setup only once, even when React runs effects twice", async () => {
    const server = stubServer(OFF, {
      "POST /api/auth/company/two-step/setup/": {
        body: { secret: "ABCDEFGH", uri: "otpauth://x" },
      },
    });
    render(
      <StrictMode>
        <TwoStepSettings />
      </StrictMode>,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Set up two-step verification" }),
    );
    await screen.findByAltText("QR code for your authenticator app");
    expect(callsTo(server, "POST", "/two-step/setup/")).toHaveLength(1);
  });
});
