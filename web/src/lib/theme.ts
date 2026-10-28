export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "bera-theme";
export const DEFAULT_THEME: Theme = "light";

/** Anything other than a saved "dark" means light, so a bad value never breaks the page. */
export function parseTheme(value: unknown): Theme {
  return value === "dark" ? "dark" : DEFAULT_THEME;
}

/** Storage can be blocked or throw (private windows, blocked cookies); never let that matter. */
export function readStoredTheme(storage: Pick<Storage, "getItem"> = window.localStorage): Theme {
  try {
    return parseTheme(storage.getItem(THEME_STORAGE_KEY));
  } catch {
    return DEFAULT_THEME;
  }
}

export function storeTheme(theme: Theme, storage: Pick<Storage, "setItem"> = window.localStorage) {
  try {
    storage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The choice still applies to this visit; it just is not remembered.
  }
}

export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement) {
  root.dataset.theme = theme;
}

/** Runs before the first paint so a saved dark choice never flashes light. */
export const themeInitScript = `try{var t=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});document.documentElement.dataset.theme=t==="dark"?"dark":"${DEFAULT_THEME}"}catch(e){document.documentElement.dataset.theme="${DEFAULT_THEME}"}`;
