import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { THEME_STORAGE_KEY } from "@/lib/theme";

import { ThemeSync } from "./ThemeSync";

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("ThemeSync", () => {
  it("puts the saved dark theme back on the page when it mounts", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(document.documentElement.dataset.theme).toBeUndefined();

    render(<ThemeSync />);

    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("uses light when nothing is saved", () => {
    render(<ThemeSync />);
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
