/** The made-up people the home page's live screening walks through. They are obviously fake. */

export type RequirementResult = "met" | "partly" | "missing";

export const RESULT_WORD: Record<RequirementResult, string> = {
  met: "Met",
  partly: "Partly",
  missing: "Missing",
};

export type DemoProfile = {
  name: string;
  role: string;
  initials: string;
  tint: "lime" | "lilac" | "peach" | "sky" | "pink";
  requirements: readonly [string, RequirementResult][];
  score: number;
  /** The button the cursor presses, and the stage it moves the candidate to. */
  action: string;
  stage: "shortlisted" | "interviewed" | "on_hold" | "selected";
};

/** A different field each time, so the product never looks like it is only for one kind of job. */
export const DEMO_PROFILES: readonly DemoProfile[] = [
  {
    name: "Maya Fake",
    role: "Sales Manager",
    initials: "MF",
    tint: "lime",
    requirements: [
      ["5+ years B2B sales", "met"],
      ["CRM tools", "met"],
      ["Team leadership", "partly"],
    ],
    score: 91,
    action: "Shortlist",
    stage: "shortlisted",
  },
  {
    name: "Daniel Sample",
    role: "Registered Nurse",
    initials: "DS",
    tint: "lilac",
    requirements: [
      ["Valid licence", "met"],
      ["ICU experience", "met"],
      ["BLS certified", "missing"],
    ],
    score: 84,
    action: "Interview",
    stage: "interviewed",
  },
  {
    name: "Sara Example",
    role: "Accountant",
    initials: "SE",
    tint: "peach",
    requirements: [
      ["CPA qualified", "met"],
      ["Payroll", "partly"],
      ["ERP software", "met"],
    ],
    score: 78,
    action: "Hold",
    stage: "on_hold",
  },
  {
    name: "Omar Testcase",
    role: "Product Designer",
    initials: "OT",
    tint: "sky",
    requirements: [
      ["Portfolio", "met"],
      ["Figma", "met"],
      ["User research", "partly"],
    ],
    score: 88,
    action: "Select",
    stage: "selected",
  },
  {
    name: "Lina Placeholder",
    role: "Logistics Coordinator",
    initials: "LP",
    tint: "pink",
    requirements: [
      ["Route planning", "met"],
      ["Warehouse systems", "partly"],
      ["Fleet safety", "met"],
    ],
    score: 86,
    action: "Shortlist",
    stage: "shortlisted",
  },
  {
    name: "Ali Demo",
    role: "Backend Developer",
    initials: "AD",
    tint: "lime",
    requirements: [
      ["Python", "met"],
      ["PostgreSQL", "met"],
      ["Cloud", "partly"],
    ],
    score: 92,
    action: "Shortlist",
    stage: "shortlisted",
  },
];

/** The grade a score earns in the demo (the real bands live on the server). */
export const demoGrade = (score: number) => (score >= 90 ? "A" : "B");

/** How long the screening waits before moving to the next stage, in milliseconds. */
export const STAGE_DWELL_MS = [450, 750, 420, 420, 420, 800, 1150, 200, 750, 1100, 450] as const;
/** The stages in order; the last one hands over to the next candidate. */
export const STAGES_IN_ORDER = [
  "enter",
  "scan",
  "requirement-1",
  "requirement-2",
  "requirement-3",
  "score",
  "cursor-moves",
  "click",
  "decided",
  "cursor-leaves",
  "leave",
] as const;
