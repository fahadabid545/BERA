import { describe, expect, it } from "vitest";

import { tintAt } from "./tints";

describe("tintAt", () => {
  it("takes turns through five colours, so neighbours differ", () => {
    const first = [0, 1, 2, 3, 4].map(tintAt);
    expect(new Set(first).size).toBe(5);
    expect(tintAt(5)).toBe(tintAt(0));
    expect(tintAt(6)).not.toBe(tintAt(5));
  });
});
