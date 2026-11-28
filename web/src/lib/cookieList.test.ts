// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { THEME_STORAGE_KEY } from "./theme";

const REMINDER =
  " Update docs/cookies.json. If it is not essential, a cookie notice (BERA-176) is required before release.";
const LIST: { name: string; storage: string; set_by: string }[] = JSON.parse(
  readFileSync(path.join(process.cwd(), "..", "docs", "cookies.json"), "utf8"),
);
const SOURCE = path.join(process.cwd(), "src");

function sourceFiles(directory = SOURCE): string[] {
  return readdirSync(directory).flatMap((name) => {
    const full = path.join(directory, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

describe("browser storage", () => {
  it("the theme key is on the list", () => {
    expect(
      LIST.some((item) => item.storage === "localStorage" && item.name === THEME_STORAGE_KEY),
    ).toBe(true);
  });

  it("only the known files use browser storage or write cookies", () => {
    const allowed = [
      "lib/theme.ts",
      "lib/api.ts",
      "lib/publicChat.ts",
      "lib/betaFeedbackDay.ts",
      "lib/hiddenColumns.ts",
    ];
    const using = sourceFiles().filter((file) =>
      /localStorage|sessionStorage|indexedDB|document\.cookie/.test(readFileSync(file, "utf8")),
    );
    const unknown = using
      .map((file) => path.relative(SOURCE, file).split(path.sep).join("/"))
      .filter((file) => !allowed.includes(file));
    expect(unknown, `${unknown} uses browser storage.` + REMINDER).toEqual([]);
  });

  it("the public chat's storage key is on the list", () => {
    const source = readFileSync(path.join(SOURCE, "lib", "publicChat.ts"), "utf8");
    const key = /STORAGE_KEY\s*=\s*"([^"]+)"/.exec(source)?.[1];
    expect(LIST.some((item) => item.storage === "localStorage" && item.name === key)).toBe(true);
  });

  it("the beta feedback storage key is on the list", () => {
    const source = readFileSync(path.join(SOURCE, "lib", "betaFeedbackDay.ts"), "utf8");
    const key = /STORAGE_KEY\s*=\s*"([^"]+)"/.exec(source)?.[1];
    expect(LIST.some((item) => item.storage === "localStorage" && item.name === key)).toBe(true);
  });

  it("the matrix column choice's storage key is on the list", () => {
    const source = readFileSync(path.join(SOURCE, "lib", "hiddenColumns.ts"), "utf8");
    const prefix = /`([^`:]+):\$\{projectId\}`/.exec(source)?.[1];
    expect(
      LIST.some(
        (item) => item.storage === "localStorage" && item.name === `${prefix}:<project id>`,
      ),
    ).toBe(true);
  });

  it("never writes a cookie from page scripts", () => {
    const writing = sourceFiles().filter((file) =>
      /document\.cookie\s*=[^=]/.test(readFileSync(file, "utf8")),
    );
    expect(writing, "A page script writes a cookie." + REMINDER).toEqual([]);
  });

  it("the cookie the page reads (the CSRF copy) is on the list", () => {
    const api = readFileSync(path.join(SOURCE, "lib", "api.ts"), "utf8");
    const name = /CSRF_COOKIE\s*=\s*"([^"]+)"/.exec(api)?.[1];
    expect(LIST.some((item) => item.storage === "cookie" && item.name === name)).toBe(true);
  });
});
