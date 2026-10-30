import { describe, expect, it } from "vitest";

import { COUNTRY_CODES, countryOptions, isCountryCode, OTHER_COUNTRY } from "./countries";

describe("countries", () => {
  it("has every country once, as two capital letters", () => {
    expect(new Set(COUNTRY_CODES).size).toBe(COUNTRY_CODES.length);
    expect(COUNTRY_CODES.every((code) => /^[A-Z]{2}$/.test(code))).toBe(true);
    expect(COUNTRY_CODES).toHaveLength(249);
  });

  it("names them in English, sorted, with Other last", () => {
    const options = countryOptions();
    const labels = options.slice(0, -1).map((option) => option.label);
    expect(options.at(-1)).toEqual({ value: OTHER_COUNTRY, label: "Other" });
    expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b, "en")));
    expect(options.find((option) => option.value === "PK")?.label).toBe("Pakistan");
  });

  it("recognises only real codes and Other", () => {
    expect(isCountryCode("PK")).toBe(true);
    expect(isCountryCode(OTHER_COUNTRY)).toBe(true);
    for (const value of ["XX", "pk", "", null, 5, "Pakistan"])
      expect(isCountryCode(value)).toBe(false);
  });
});
