import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TwoStepLogin } from "./TwoStepLogin";

function stubServer(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function open() {
  const handlers = { onSignedIn: vi.fn(), onStartOver: vi.fn() };
  render(<TwoStepLogin challenge="signed-challenge" {...handlers} />);
  return handlers;
}

afterEach(() => vi.unstubAllGlobals());

describe("two-step login", () => {
  it("sends the challenge with the code and signs in", async () => {
    const server = stubServer(200, { status: "ok" });
    const { onSignedIn } = open();
    await userEvent.type(screen.getByLabelText("Code from your app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await vi.waitFor(() => expect(onSignedIn).toHaveBeenCalledOnce());
    const [path, init] = server.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/login/two-step/");
    expect(JSON.parse(String(init.body))).toEqual({
      challenge: "signed-challenge",
      code: "123456",
    });
  });

  it("can switch to a recovery code and back", async () => {
    stubServer(200, { status: "ok" });
    open();
    await userEvent.click(screen.getByRole("button", { name: "Use a recovery code" }));
    expect(screen.getByLabelText("Recovery code")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Use the code from my app" }));
    expect(screen.getByLabelText("Code from your app")).toBeTruthy();
  });

  it("shows a wrong code in plain words and does not sign in", async () => {
    stubServer(400, {
      error: {
        code: "two_step_code_wrong",
        message: "That code is not correct. Try again.",
        fields: { code: "That code is not correct. Try again." },
      },
    });
    const { onSignedIn } = open();
    await userEvent.type(screen.getByLabelText("Code from your app"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("That code is not correct. Try again.")).toBeTruthy();
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("offers going back to the login when the step has ended", async () => {
    stubServer(400, {
      error: {
        code: "two_step_challenge_ended",
        message: "Your login took too long. Please log in again.",
      },
    });
    const { onStartOver } = open();
    await userEvent.type(screen.getByLabelText("Code from your app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await userEvent.click(await screen.findByRole("button", { name: "Back to login" }));
    expect(onStartOver).toHaveBeenCalledOnce();
  });

  it("tells a person who lost the device and the codes to contact support", () => {
    stubServer(200, {});
    open();
    expect(screen.getByText(/Lost your device and your recovery codes/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Contact support" }).getAttribute("href")).toBe(
      "/contact",
    );
  });
});
