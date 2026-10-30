"use client";

import { useEffect } from "react";

import { applyTheme, readStoredTheme } from "@/lib/theme";

/**
 * Re-applies the saved theme once the page is running. Next rebuilds <html> when it shows a
 * not-found page inside a nested layout, which drops what the start-up script set.
 */
export function ThemeSync() {
  useEffect(() => applyTheme(readStoredTheme()), []);
  return null;
}
