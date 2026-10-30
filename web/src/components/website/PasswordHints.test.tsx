import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PasswordHints } from "./PasswordHints";

const RULES = (minimumMet: boolean, commonMet: boolean) => ({
  rules: [
    { id: "min_length", text: "At least 12 characters", met: minimumMet },
    { id: "max_length", text: "At most 128 characters", met: true },
    { id: "not_common", text: "Not a commonly used password", met: commonMet },
  ],
});

function stubServer(answer: (password: string) => object | "down") {
  const fetchMock = vi.fn(async (_path: string, init?: RequestInit) => {
    const reply = answer(JSON.parse(String(init?.body)).password);
    if (reply === "down") throw new TypeError("down");
    return new Response(JSON.stringify(reply), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("live password hints", () => {
  it("lists every rule, as met or not met, before anything is typed", async () => {
    stubServer(() => RULES(false, true));
    render(<PasswordHints password="" />);
    expect(await screen.findByText("At least 12 characters: not met")).toBeTruthy();
    expect(screen.getByText("At most 128 characters: met")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Password rules" }).children).toHaveLength(3);
  });

  it("asks the server what has been typed, after a short pause", async () => {
    const server = stubServer((password) =>
      password === "password" ? RULES(false, false) : RULES(true, true),
    );
    const { rerender } = render(<PasswordHints password="" />);
    await screen.findByText("At least 12 characters: met");
    rerender(<PasswordHints password="password" />);
    expect(server).toHaveBeenCalledTimes(1); // not on every keystroke
    await act(async () => {
      await vi.advanceTimersByTimeAsync(450);
    });
    expect(await screen.findByText("Not a commonly used password: not met")).toBeTruthy();
    expect(JSON.parse(String(server.mock.calls[1][1]?.body))).toEqual({ password: "password" });
  });

  it("only asks once while typing continues", async () => {
    const server = stubServer(() => RULES(true, true));
    const { rerender } = render(<PasswordHints password="" />);
    await screen.findByText("At least 12 characters: met");
    for (const typed of ["a", "ab", "abc", "abcd"]) {
      rerender(<PasswordHints password={typed} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
    }
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(server).toHaveBeenCalledTimes(2); // empty, then the final text
  });

  it("never shows an answer that belongs to older text", async () => {
    let releaseFirst: (reply: Response) => void = () => {};
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (releaseFirst = resolve)))
      .mockImplementation(
        async () => new Response(JSON.stringify(RULES(true, true)), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<PasswordHints password="" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10); // the first question is on its way
    });
    rerender(<PasswordHints password="newer text here" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(450);
    });
    await screen.findByText("At least 12 characters: met");
    releaseFirst(new Response(JSON.stringify(RULES(false, false)), { status: 200 }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("At least 12 characters: met")).toBeTruthy();
  });

  it("shows nothing when the check cannot be reached, so the form still works", async () => {
    stubServer(() => "down");
    render(<PasswordHints password="anything long enough" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    await waitFor(() => expect(screen.queryByRole("list")).toBeNull());
  });

  it("uses words, not only colour, to tell met from not met", async () => {
    stubServer(() => RULES(false, true));
    render(<PasswordHints password="" />);
    const items = (await screen.findAllByRole("listitem")).map((item) => item.textContent);
    expect(items.some((text) => text?.endsWith(": met"))).toBe(true);
    expect(items.some((text) => text?.endsWith(": not met"))).toBe(true);
  });
});
