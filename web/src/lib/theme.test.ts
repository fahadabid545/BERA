import { describe, expect, it } from "vitest";

import {
  applyTheme,
  parseTheme,
  readStoredTheme,
  storeTheme,
  themeInitScript,
  THEME_STORAGE_KEY,
} from "./theme";

const storageWith = (value: string | null) => ({ getItem: () => value });
const brokenStorage = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
};

describe("theme", () => {
  it("is light unless dark was saved", () => {
    expect(readStoredTheme(storageWith(null))).toBe("light");
    expect(readStoredTheme(storageWith("dark"))).toBe("dark");
  });

  it.each(["", "DARK", "blue", "undefined"])("treats the saved value %j as light", (value) => {
    expect(parseTheme(value)).toBe("light");
  });

  it("falls back to light when storage is blocked", () => {
    expect(readStoredTheme(brokenStorage)).toBe("light");
  });

  it("does not fail when the choice cannot be saved", () => {
    expect(() => storeTheme("dark", brokenStorage)).not.toThrow();
  });

  it("remembers the choice under one key", () => {
    const saved: Record<string, string> = {};
    storeTheme("dark", { setItem: (key, value) => void (saved[key] = value) });
    expect(saved).toEqual({ [THEME_STORAGE_KEY]: "dark" });
  });

  it("applies the theme to the page", () => {
    const root = document.createElement("html");
    applyTheme("dark", root);
    expect(root.dataset.theme).toBe("dark");
  });

  it("has a start-up script that applies the saved theme before first paint", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    new Function(themeInitScript)();
    expect(document.documentElement.dataset.theme).toBe("dark");

    window.localStorage.setItem(THEME_STORAGE_KEY, "nonsense");
    new Function(themeInitScript)();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
