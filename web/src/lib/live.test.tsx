import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OfflineNotice } from "@/components/company/OfflineNotice";

import type { ApiResult } from "./api";
import { startLive } from "./live";

type Answer = { refresh_seconds: number; n: number };
const good = (n = 1): ApiResult<Answer> => ({ ok: true, data: { refresh_seconds: 3, n } });
const lost: ApiResult<Answer> = { ok: false, error: { code: "unreachable", message: "x" } };
const tooMany = (wait: number): ApiResult<Answer> => ({
  ok: false,
  error: { code: "too_many_requests", message: "x", details: { retry_after_seconds: wait } },
});
const refused: ApiResult<Answer> = { ok: false, error: { code: "not_found", message: "x" } };

let hidden = false;
const stoppers: (() => void)[] = [];
function start(load: () => Promise<ApiResult<Answer>>, onResult = vi.fn()) {
  const stop = startLive(load, onResult);
  stoppers.push(stop);
  return { stop, onResult };
}
const later = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

beforeEach(() => {
  vi.useFakeTimers();
  hidden = false;
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  vi.spyOn(Math, "random").mockReturnValue(0);
});
afterEach(() => {
  stoppers.splice(0).forEach((stop) => stop());
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("live updates", () => {
  it("asks at once and then every refresh_seconds the server names", async () => {
    const load = vi.fn().mockResolvedValue(good());
    start(load);
    await later(0);
    expect(load).toHaveBeenCalledTimes(1);
    await later(2900);
    expect(load).toHaveBeenCalledTimes(1);
    await later(200);
    expect(load).toHaveBeenCalledTimes(2);
    await later(3000);
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("never waits longer than the server's delay, whatever the chance", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0.999);
    const load = vi.fn().mockResolvedValue(good());
    start(load);
    await later(0);
    await later(3000);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("gives every answer to the screen, so changes arrive within the delay", async () => {
    let n = 0;
    const { onResult } = start(async () => good(++n));
    await later(0);
    await later(3000);
    expect(onResult.mock.calls.map((call) => call[0].data.n)).toEqual([1, 2]);
  });

  it("stops when asked", async () => {
    const load = vi.fn().mockResolvedValue(good());
    const { stop } = start(load);
    await later(0);
    stop();
    await later(20000);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("does not ask while the tab is hidden and asks at once when it is shown", async () => {
    const load = vi.fn().mockResolvedValue(good());
    start(load);
    await later(0);
    hidden = true;
    document.dispatchEvent(new Event("visibilitychange"));
    await later(60000);
    expect(load).toHaveBeenCalledTimes(1);
    hidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
    await later(0);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("never runs two asks at once", async () => {
    let release: (value: ApiResult<Answer>) => void = () => {};
    const load = vi.fn().mockImplementation(() => new Promise((resolve) => (release = resolve)));
    start(load);
    await later(0);
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("online"));
    await later(0);
    expect(load).toHaveBeenCalledTimes(1);
    release(good());
  });

  it("stops after a refusal that is not a lost connection", async () => {
    const load = vi.fn().mockResolvedValue(refused);
    start(load);
    await later(0);
    await later(60000);
    expect(load).toHaveBeenCalledTimes(1);
  });
});

describe("asking too often", () => {
  it("waits at least as long as the server says and is not shown as offline", async () => {
    const answers = [tooMany(20)];
    const load = vi.fn().mockImplementation(async () => answers.shift() ?? good());
    start(load);
    render(<OfflineNotice />);
    await later(0);
    await later(15000);
    expect(load).toHaveBeenCalledTimes(1);
    await later(6000);
    expect(load).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Offline")).toBeNull();
  });
});

describe("a lost connection", () => {
  it("shows Offline, waits longer and longer, and catches up when back", async () => {
    const answers = [good(), lost, lost, lost, good(2)];
    const load = vi.fn().mockImplementation(async () => answers.shift() ?? good(9));
    const { onResult } = start(load);
    render(<OfflineNotice />);
    await later(0);
    expect(screen.queryByText("Offline")).toBeNull();
    await later(3000);
    expect(screen.getByRole("status").textContent).toBe("Offline");
    expect(load).toHaveBeenCalledTimes(2);
    await later(3000);
    expect(load).toHaveBeenCalledTimes(2);
    await later(3000);
    expect(load).toHaveBeenCalledTimes(3);
    await later(12000);
    expect(load).toHaveBeenCalledTimes(4);
    await later(24000);
    expect(load.mock.calls.length).toBeGreaterThanOrEqual(5);
    expect(screen.queryByText("Offline")).toBeNull();
    expect(onResult.mock.calls.at(-1)?.[0].ok).toBe(true);
  });

  it("the backoff has a ceiling", async () => {
    const load = vi.fn().mockResolvedValue(lost);
    start(load);
    await later(0);
    for (let i = 0; i < 8; i += 1) await later(24000);
    const before = load.mock.calls.length;
    await later(24000);
    expect(load.mock.calls.length).toBe(before + 1);
  });

  it("asks at once when the browser says it is back online", async () => {
    const answers = [lost];
    const load = vi.fn().mockImplementation(async () => answers.shift() ?? good());
    start(load);
    render(<OfflineNotice />);
    await later(0);
    expect(screen.getByRole("status").textContent).toBe("Offline");
    window.dispatchEvent(new Event("online"));
    await later(0);
    expect(load).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Offline")).toBeNull();
  });

  it("shows Offline when the browser reports it, even before an ask fails", async () => {
    render(<OfflineNotice />);
    expect(screen.queryByText("Offline")).toBeNull();
    act(() => void window.dispatchEvent(new Event("offline")));
    expect(screen.getByRole("status").textContent).toBe("Offline");
    act(() => void window.dispatchEvent(new Event("online")));
    expect(screen.queryByText("Offline")).toBeNull();
  });

  it("leaving the screen clears its part of the Offline notice", async () => {
    const { stop } = start(vi.fn().mockResolvedValue(lost));
    render(<OfflineNotice />);
    await later(0);
    expect(screen.getByRole("status")).toBeTruthy();
    act(() => stop());
    expect(screen.queryByText("Offline")).toBeNull();
  });
});
