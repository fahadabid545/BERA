import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AiPlayground } from "./AiPlayground";

const fetchMock = vi.fn();
const BUDGET = {
  month: "2026-11",
  limit: "10.000000",
  spent: "2.500000",
  remaining: "7.500000",
  used_up: false,
};
const OPTIONS = {
  models: ["model-a", "model-b"],
  prompts: {
    reading: [
      { number: 1, current: false },
      { number: 2, current: true },
    ],
    scoring: [{ number: 1, current: true }],
  },
  budget: BUDGET,
};
const RESULT = {
  profile: {
    skills: ["Python", "Django"],
    jobs: [{ title: "Backend Engineer", start: "2018", end: "present" }],
    years_of_experience: 8,
    education: [],
    certifications: [],
    languages: ["English"],
    summary: "A backend engineer.",
  },
  requirements: [
    {
      kind: "must",
      text: "Python experience",
      weight: 3,
      verdict: "met",
      evidence: "Python Django",
      confidence: "high",
    },
    {
      kind: "nice",
      text: "Kubernetes",
      weight: 3,
      verdict: "missing",
      evidence: "",
      confidence: "medium",
    },
  ],
  score: {
    score: "70.0",
    grade: "C",
    must_score: "100.0",
    nice_score: "0.0",
    capped: false,
    label: "possible",
    borderline: true,
  },
  usage: {
    steps: [
      { step: "reading", tokens_in: 1000, tokens_out: 500, cost: "0.007000" },
      { step: "requirement_extraction", tokens_in: 200, tokens_out: 100, cost: "0.001400" },
      { step: "scoring", tokens_in: 400, tokens_out: 200, cost: "0.002800" },
    ],
    tokens_in: 1600,
    tokens_out: 800,
    cost: "0.011200",
  },
  budget: { ...BUDGET, spent: "2.511200", remaining: "7.488800" },
  notice: "",
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const rowsOf = (name: string) =>
  Array.from(screen.getByRole("region", { name }).querySelectorAll("tbody tr")).map((row) =>
    Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent),
  );

async function fillAndRun() {
  const file = new File(["fake cv"], "cv.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText("CV file"), file);
  await userEvent.type(screen.getByLabelText("Job description"), "A fake job");
  await userEvent.click(screen.getByRole("button", { name: "Run test" }));
  return file;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AI playground", () => {
  it("warns not to use real candidate data", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    expect((await screen.findByRole("note")).textContent).toContain(
      "Do not use real candidate data.",
    );
  });

  it("offers the models and prompt versions, with the current version chosen", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("button", { name: "Run test" });
    const optionsOf = (label: string) =>
      Array.from((screen.getByLabelText(label) as HTMLSelectElement).options).map((o) => o.text);
    expect(optionsOf("Reading model")).toEqual(["model-a", "model-b"]);
    expect(optionsOf("Scoring model")).toEqual(["model-a", "model-b"]);
    expect(optionsOf("Reading prompt version")).toEqual(["Version 1", "Version 2 (current)"]);
    expect((screen.getByLabelText("Reading prompt version") as HTMLSelectElement).value).toBe("2");
    expect(optionsOf("Scoring prompt version")).toEqual(["Version 1 (current)"]);
  });

  it("shows the budget, what was spent and what is left", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("region", { name: "Test budget" });
    expect(rowsOf("Test budget")).toEqual([["2026-11", "$10.0000", "$2.5000", "$7.5000"]]);
  });

  it("sends the file, the description and the choices, then shows everything", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("button", { name: "Run test" });
    reply(200, RESULT);
    await userEvent.selectOptions(screen.getByLabelText("Scoring model"), "model-b");
    const file = await fillAndRun();

    await screen.findByRole("region", { name: "Score" });
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe("/api/admin/ai/playground/run/");
    const sent = init.body as FormData;
    expect(sent.get("cv_file")).toBe(file);
    expect(sent.get("job_description")).toBe("A fake job");
    expect(sent.get("reading_model")).toBe("model-a");
    expect(sent.get("scoring_model")).toBe("model-b");
    expect(sent.get("reading_prompt_version")).toBe("2");
    expect(sent.get("scoring_prompt_version")).toBe("1");

    expect(rowsOf("Score")).toEqual([["70.0", "C", "100.0", "0.0", "Possible match, borderline"]]);
    expect(rowsOf("Requirement results")).toEqual([
      ["Python experience", "Must-have", "3", "Met", "Python Django", "high"],
      ["Kubernetes", "Nice-to-have", "3", "Missing", "None", "medium"],
    ]);
    const profile = rowsOf("Profile");
    expect(profile[0]).toEqual(["Skills", "Python, Django"]);
    expect(profile[1]).toEqual(["Jobs", "Backend Engineer (2018 to present)"]);
    expect(profile[3]).toEqual(["Education", "None"]);
    expect(rowsOf("Tokens and cost")).toEqual([
      ["Reading the CV", "1000", "500", "$0.0070"],
      ["Finding the requirements", "200", "100", "$0.0014"],
      ["Judging the requirements", "400", "200", "$0.0028"],
      ["Total", "1600", "800", "$0.0112"],
    ]);
  });

  it("shows the new budget figures after a run", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("button", { name: "Run test" });
    reply(200, RESULT);
    await fillAndRun();
    await screen.findByRole("region", { name: "Score" });
    expect(rowsOf("Test budget")).toEqual([["2026-11", "$10.0000", "$2.5112", "$7.4888"]]);
  });

  it("says in plain words when a run is refused, and keeps the form", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("button", { name: "Run test" });
    reply(409, {
      error: {
        code: "playground_budget_used_up",
        message: "The test budget for this month is used up.",
        details: { ...BUDGET, spent: "10.000000", remaining: "0.000000", used_up: true },
      },
    });
    await fillAndRun();
    expect((await screen.findByRole("alert")).textContent).toBe(
      "The test budget for this month is used up.",
    );
    expect((screen.getByLabelText("Job description") as HTMLTextAreaElement).value).toBe(
      "A fake job",
    );
    expect(screen.queryByRole("region", { name: "Score" })).toBeNull();
    expect(rowsOf("Test budget")).toEqual([["2026-11", "$10.0000", "$10.0000", "$0.0000"]]);
  });

  it("cannot start a run once the budget is used up", async () => {
    reply(200, { ...OPTIONS, budget: { ...BUDGET, remaining: "0.000000", used_up: true } });
    render(<AiPlayground />);
    const button = await screen.findByRole("button", { name: "Run test" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a refused field beside it", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("button", { name: "Run test" });
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { cv_file: "This file is empty." },
      },
    });
    await fillAndRun();
    await waitFor(() =>
      expect(screen.getAllByText("This file is empty.").length).toBeGreaterThan(0),
    );
  });

  it("disables the button while a run is going", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("button", { name: "Run test" });
    let finish: (value: unknown) => void = () => {};
    fetchMock.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    await fillAndRun();
    const running = await screen.findByRole("button", { name: "Running" });
    expect((running as HTMLButtonElement).disabled).toBe(true);
    finish({ ok: true, status: 200, json: async () => RESULT });
    await screen.findByRole("region", { name: "Score" });
  });

  it("changes the monthly budget in a popup with a reason", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("region", { name: "Test budget" });
    await userEvent.click(screen.getByRole("button", { name: "Set test budget" }));
    const dialog = screen.getByRole("dialog");
    const amount = within(dialog).getByLabelText("Monthly budget (USD)") as HTMLInputElement;
    expect(amount.value).toBe("10");
    await userEvent.clear(amount);
    await userEvent.type(amount, "25");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "More tests");
    reply(200, { ...BUDGET, limit: "25.000000", remaining: "22.500000" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save budget" }));
    await waitFor(() =>
      expect(rowsOf("Test budget")).toEqual([["2026-11", "$25.0000", "$2.5000", "$22.5000"]]),
    );
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe("/api/admin/ai/playground/");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ monthly_budget: "25", reason: "More tests" });
  });

  it("shows why a budget change was refused", async () => {
    reply(200, OPTIONS);
    render(<AiPlayground />);
    await screen.findByRole("region", { name: "Test budget" });
    await userEvent.click(screen.getByRole("button", { name: "Set test budget" }));
    const dialog = screen.getByRole("dialog");
    reply(400, {
      error: { code: "validation_error", message: "Please check the form and try again." },
    });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save budget" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Please check the form and try again.",
    );
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AiPlayground />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
