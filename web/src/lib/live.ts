"use client";

import { useSyncExternalStore } from "react";

import type { ApiResult } from "@/lib/api";

/** Keeps a screen up to date without a reload. Every live screen asks again after the number of
 * seconds the server names in its answer (`refresh_seconds`, a platform setting), so the delay is
 * the server's to change.
 *
 * To keep the server calm with many open tabs:
 * - a tab that is hidden stops asking, and asks once at once when it is shown again;
 * - each wait is a little shorter by chance, so tabs opened together do not all ask at the same moment;
 * - after a lost connection the wait grows (up to a few times the normal one), and the first
 *   sign of the connection coming back (the browser's "online" event) asks at once to catch up.
 *
 * While any live screen cannot reach the server, or the browser says it is offline, the top bar
 * shows "Offline" (see `OfflineNotice`). */

const MILLISECONDS = 1000;
const UNREACHABLE = "unreachable";
const TOO_MANY = "too_many_requests";
/** Used only until the server has named the delay (the first answer has not arrived yet). */
const UNTIL_KNOWN_SECONDS = 3;
const MAX_BACKOFF_FACTOR = 8;
const JITTER = 0.2;

const lost = new Set<symbol>();
const listeners = new Set<() => void>();
let browserOffline = typeof navigator !== "undefined" && navigator.onLine === false;

const announce = () => listeners.forEach((listener) => listener());

function setLost(source: symbol, isLost: boolean) {
  if (isLost === lost.has(source)) return;
  if (isLost) lost.add(source);
  else lost.delete(source);
  announce();
}

if (typeof window !== "undefined") {
  window.addEventListener("offline", () => {
    browserOffline = true;
    announce();
  });
  window.addEventListener("online", () => {
    browserOffline = false;
    announce();
  });
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

/** True while a live screen cannot reach the server or the browser is offline. */
export function useOffline() {
  return useSyncExternalStore(
    subscribe,
    () => browserOffline || lost.size > 0,
    () => false,
  );
}

/** Asks `load` now and then again and again, giving each answer to `onResult`. Returns the
 * function that stops it. After an answer that is neither good, "unreachable" nor "too many requests" (a refusal such
 * as not found), it stops asking: the person has something to read or do first. */
export function startLive<T extends { refresh_seconds: number }>(
  load: () => Promise<ApiResult<T>>,
  onResult: (result: ApiResult<T>) => void,
) {
  const source = Symbol("live");
  let stopped = false;
  let running = false;
  let failures = 0;
  let seconds = UNTIL_KNOWN_SECONDS;
  let timer: ReturnType<typeof setTimeout> | undefined;

  let askedToWait = 0;
  const waitMilliseconds = () => {
    const factor = Math.min(2 ** failures, MAX_BACKOFF_FACTOR);
    // Only ever shorter, so an update never arrives later than the server's delay.
    const spread = 1 - Math.random() * JITTER;
    return Math.max(seconds * MILLISECONDS * factor * spread, askedToWait);
  };
  const schedule = () => {
    clearTimeout(timer);
    if (!stopped && !document.hidden) timer = setTimeout(() => void poll(), waitMilliseconds());
  };
  async function poll() {
    clearTimeout(timer);
    if (stopped || running) return;
    running = true;
    const result = await load();
    running = false;
    if (stopped) return;
    onResult(result);
    askedToWait = 0;
    if (result.ok) {
      failures = 0;
      seconds = result.data.refresh_seconds;
      setLost(source, false);
    } else if (result.error.code === UNREACHABLE) {
      failures += 1;
      setLost(source, true);
    } else if (result.error.code === TOO_MANY) {
      // Asking too often: wait as long as the server says, longer if it keeps happening.
      failures += 1;
      askedToWait = Number(result.error.details?.retry_after_seconds ?? 0) * MILLISECONDS;
    } else {
      setLost(source, false);
      return;
    }
    schedule();
  }

  const shownAgain = () => {
    if (document.hidden) clearTimeout(timer);
    else void poll();
  };
  const backOnline = () => {
    failures = 0;
    void poll();
  };
  document.addEventListener("visibilitychange", shownAgain);
  window.addEventListener("online", backOnline);
  void poll();

  return () => {
    stopped = true;
    clearTimeout(timer);
    setLost(source, false);
    document.removeEventListener("visibilitychange", shownAgain);
    window.removeEventListener("online", backOnline);
  };
}
