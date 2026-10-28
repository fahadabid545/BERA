"use client";

import { useEffect, useState } from "react";

import { applyTheme, readStoredTheme, storeTheme, type Theme } from "@/lib/theme";

/** Light/dark switch. The choice is remembered in this browser. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => setTheme(readStoredTheme()), []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    storeTheme(next);
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={theme === "dark"}
      className="ui-switch"
      onClick={toggle}
    >
      <span className="ui-switch__track" aria-hidden="true">
        <span className="ui-switch__thumb" />
      </span>
      Dark mode
    </button>
  );
}
