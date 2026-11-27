import { describe, expect, it } from "vitest";

import { STAGES } from "@/components/company/stages";

import { DEMO_PROFILES, STAGES_IN_ORDER, STAGE_DWELL_MS, demoGrade } from "./demo";

describe("home page demo data", () => {
  it("waits a set time for every stage", () => {
    expect(STAGE_DWELL_MS).toHaveLength(STAGES_IN_ORDER.length);
    for (const ms of STAGE_DWELL_MS) expect(ms).toBeGreaterThan(0);
  });

  it("covers several different fields, not only software roles", () => {
    const roles = DEMO_PROFILES.map((profile) => profile.role);
    expect(new Set(roles).size).toBe(roles.length);
    expect(roles.filter((role) => /developer|engineer/i.test(role)).length).toBeLessThanOrEqual(1);
  });

  it("gives every person three requirements, a score from 0 to 100 and a real hiring stage", () => {
    const realStages = STAGES.map((stage) => stage.value);
    for (const profile of DEMO_PROFILES) {
      expect(profile.requirements).toHaveLength(3);
      expect(profile.score).toBeGreaterThanOrEqual(0);
      expect(profile.score).toBeLessThanOrEqual(100);
      expect(realStages).toContain(profile.stage);
    }
  });

  it("uses obviously fake names", () => {
    const names = DEMO_PROFILES.map((profile) => profile.name).join(" ");
    expect(names).toMatch(/Fake|Sample|Example|Testcase|Placeholder|Demo/);
  });

  it("shows several different decisions", () => {
    expect(new Set(DEMO_PROFILES.map((profile) => profile.stage)).size).toBeGreaterThanOrEqual(4);
  });

  it("grades 90 and above as A", () => {
    expect(demoGrade(90)).toBe("A");
    expect(demoGrade(89)).toBe("B");
  });
});
