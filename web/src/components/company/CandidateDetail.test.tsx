import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateDetail } from "./CandidateDetail";

const fetchMock = vi.fn();
const URL = "/api/company/projects/p1/candidates/k1/";

const detail = (over: object = {}) => ({
  id: "k1",
  file_name: "jane.pdf",
  status: "done",
  failure_reason: "",
  stage: "new",
  added_at: "2026-11-14T10:00:00Z",
  contact: { name: "Jane Example", email: "jane@example.com", phone: "", address: "" },
  score: {
    score: "82.5",
    grade: "B",
    capped: false,
    outdated: false,
    must_score: "90.0",
    nice_score: "60.0",
    label: "strong_match",
    borderline: false,
    strengths: ["Strong Python"],
    risks: ["No cloud"],
    interview_questions: ["Why us?"],
    guide_note: "Check cloud.",
  },
  ats: { score: 71, reasons: ["Clear headings"], rules_version: 1 },
  requirements: [
    {
      requirement_id: "r1", text: "Python", kind: "must", weight: 5, verdict: "met",
      evidence: "five years of Python", confidence: "high", outdated: false,
    },
    {
      requirement_id: "r2", text: "Kubernetes", kind: "nice", weight: 2, verdict: null,
      evidence: "", confidence: null, outdated: true,
    },
  ],
  factors: {
    outdated: false,
    values: { seniority: { value: 80, explanation: "Senior titles" }, recency: { value: null, explanation: "No dates" } },
  },
  history: [],
  notes: [],
  models: { reading: { model: "gpt-read", prompt_version: 2 }, scoring: { model: "gpt-score", prompt_version: 7 } },
  cv: { file_type: "pdf", can_preview: true },
  ...over,
}); // prettier-ignore

function serve(body: unknown, ok = true, status = 200) {
  fetchMock.mockResolvedValue({ ok, status, json: async () => body });
}
const open = async () => {
  render(<CandidateDetail projectId="p1" candidateId="k1" />);
  return screen.findByRole("heading", { name: "jane.pdf" });
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("candidate detail", () => {
  it("asks for the candidate of the project", async () => {
    serve(detail());
    await open();
    expect(fetchMock.mock.calls[0][0]).toBe(URL);
  });

  it("shows the contact details, stage and date", async () => {
    serve(detail());
    await open();
    expect(screen.getByText("jane@example.com")).toBeTruthy();
    expect(screen.getByText(/Stage: New/)).toBeTruthy();
    expect(screen.getByText(/2026-11-14/)).toBeTruthy();
  });

  it("shows the score, grade, label and group scores", async () => {
    serve(detail());
    await open();
    const card = screen.getByRole("region", { name: "Score" });
    expect(card.textContent).toContain("82.5 (B) Strong match");
    expect(card.textContent).toContain("Must-haves: 90.0");
    expect(card.textContent).toContain("Nice-to-haves: 60.0");
    expect(card.textContent).toContain("Check cloud.");
  });

  it("marks the tags Borderline, Capped and Outdated", async () => {
    serve(detail({ score: { ...detail().score, borderline: true, capped: true, outdated: true } }));
    await open();
    const card = within(screen.getByRole("region", { name: "Score" }));
    ["Borderline", "Capped", "Outdated"].forEach((tag) => expect(card.getByText(tag)).toBeTruthy());
  });

  it("shows the ATS score and its reasons", async () => {
    serve(detail());
    await open();
    const card = screen.getByRole("region", { name: "ATS score" });
    expect(card.textContent).toContain("71");
    expect(card.textContent).toContain("Clear headings");
  });

  it("shows each requirement with its result and evidence quote", async () => {
    serve(detail());
    await open();
    const table = screen.getByRole("region", { name: "Requirements" });
    const rows = within(table).getAllByRole("row");
    expect(rows[1].textContent).toContain("five years of Python");
    expect(rows[1].textContent).toContain("Met");
    expect(rows[1].textContent).toContain("Must-have");
  });

  it("marks a requirement not judged yet", async () => {
    serve(detail());
    await open();
    const rows = within(screen.getByRole("region", { name: "Requirements" })).getAllByRole("row");
    expect(rows[2].textContent).toContain("Not judged");
  });

  it("marks a result judged against older wording", async () => {
    const base = detail();
    serve(detail({ requirements: [{ ...base.requirements[0], outdated: true }] }));
    await open();
    const rows = within(screen.getByRole("region", { name: "Requirements" })).getAllByRole("row");
    expect(rows[1].textContent).toContain("Met");
    expect(within(rows[1]).getByText("Outdated")).toBeTruthy();
  });

  it("shows strengths, risks and interview questions", async () => {
    serve(detail());
    await open();
    expect(
      within(screen.getByRole("region", { name: "Strengths" })).getByText("Strong Python"),
    ).toBeTruthy();
    expect(
      within(screen.getByRole("region", { name: "Risks" })).getByText("No cloud"),
    ).toBeTruthy();
    expect(
      within(screen.getByRole("region", { name: "Interview questions" })).getByText("Why us?"),
    ).toBeTruthy();
  });

  it("shows the extra factors, with Not found for a missing value", async () => {
    serve(detail());
    await open();
    const table = screen.getByRole("region", { name: "Extra factors" });
    expect(table.textContent).toContain("Seniority fit");
    expect(table.textContent).toContain("80");
    expect(table.textContent).toContain("Not found");
  });

  it("marks factors from an older job description", async () => {
    serve(detail({ factors: { ...detail().factors, outdated: true } }));
    await open();
    expect(
      within(screen.getByRole("region", { name: "Extra factors" })).getAllByText("Outdated"),
    ).toHaveLength(2);
  });

  it("shows no factors table when none are stored", async () => {
    serve(detail({ factors: null }));
    await open();
    expect(screen.queryByRole("region", { name: "Extra factors" })).toBeNull();
  });

  it("shows notes", async () => {
    serve(
      detail({
        notes: [
          {
            id: "n1",
            text: "Call on Monday",
            author: "Omar",
            mine: false,
            created_at: "2026-11-14T10:00:00Z",
            updated_at: "2026-11-14T10:00:00Z",
          },
        ],
      }),
    );
    await open();
    expect(screen.getByText("Call on Monday")).toBeTruthy();
  });

  it("shows the model and prompt version used", async () => {
    serve(detail());
    await open();
    const card = screen.getByRole("region", { name: "Models" });
    expect(card.textContent).toContain("Reading: gpt-read, prompt version 2");
    expect(card.textContent).toContain("Scoring: gpt-score, prompt version 7");
  });

  it("previews a PDF and offers the download", async () => {
    serve(detail());
    await open();
    expect(screen.getByTitle("CV preview").getAttribute("src")).toBe(`${URL}cv/`);
    expect(screen.getByRole("link", { name: "Download CV" }).getAttribute("href")).toBe(
      `${URL}cv/?download=1`,
    );
  });

  it("offers only the download for a file that cannot be previewed", async () => {
    serve(detail({ cv: { file_type: "docx", can_preview: false } }));
    await open();
    expect(screen.queryByTitle("CV preview")).toBeNull();
    expect(screen.getByRole("link", { name: "Download CV" })).toBeTruthy();
  });

  it("a failed candidate says so with the reason", async () => {
    serve(detail({ status: "failed", failure_reason: "AI scoring failed. Try again." }));
    await open();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText(/AI scoring failed/)).toBeTruthy();
  });

  it("a candidate not scored yet says so", async () => {
    serve(detail({ score: null, ats: null, status: "scoring" }));
    await open();
    expect(screen.getByText("Not scored yet.")).toBeTruthy();
    expect(screen.getByText("Scoring")).toBeTruthy();
  });

  it("a deleted candidate shows a clear message", async () => {
    serve({ error: { code: "not_found", message: "Not found." } }, false, 404);
    render(<CandidateDetail projectId="p1" candidateId="k1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("This candidate no longer exists.");
  });

  it("another failure shows the server's message", async () => {
    serve({ error: { code: "internal_error", message: "Something went wrong." } }, false, 500);
    render(<CandidateDetail projectId="p1" candidateId="k1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});

describe("stage, history and notes", () => {
  const note = (over: object = {}) => ({
    id: "n1",
    text: "Call on Monday",
    author: "Omar",
    mine: true,
    created_at: "2026-11-14T10:00:00Z",
    updated_at: "2026-11-14T10:00:00Z",
    ...over,
  });
  const sent = () =>
    fetchMock.mock.calls.filter((call) => call[1]?.method && call[1].method !== "GET");

  it("shows the history with who and when", async () => {
    serve(
      detail({
        history: [
          { from_stage: "new", to_stage: "shortlisted", by: "Omar", at: "2026-11-14T11:00:00Z" },
        ],
      }),
    );
    await open();
    const card = screen.getByRole("region", { name: "Stage history" });
    expect(card.textContent).toContain("New to Shortlisted by Omar, 2026-11-14");
  });

  it("says when nothing has changed yet", async () => {
    serve(detail());
    await open();
    expect(screen.getByRole("region", { name: "Stage history" }).textContent).toContain(
      "No changes.",
    );
  });

  it("changes the stage after a confirmation", async () => {
    serve(detail());
    await open();
    const user = userEvent.setup();
    const button = screen.getByRole("button", { name: "Change stage" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    await user.selectOptions(screen.getByLabelText("Stage"), "approved");
    await user.click(button);
    const dialog = await screen.findByRole("dialog", { name: "Change stage" });
    expect(dialog.textContent).toContain("Move this candidate to Approved?");
    expect(sent()).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Change stage" }));
    await waitFor(() => expect(sent()).toHaveLength(1));
    expect(sent()[0][0]).toBe("/api/company/projects/p1/candidates/stage/");
    expect(JSON.parse(sent()[0][1].body)).toEqual({ candidate_ids: ["k1"], stage: "approved" });
  });

  it("adds a note", async () => {
    serve(detail());
    await open();
    const user = userEvent.setup();
    const add = screen.getByRole("button", { name: "Add note" }) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    await user.type(screen.getByLabelText("New note"), "Strong referee");
    await user.click(add);
    await waitFor(() => expect(sent()).toHaveLength(1));
    expect(sent()[0][0]).toBe(`${URL}notes/`);
    expect(JSON.parse(sent()[0][1].body)).toEqual({ text: "Strong referee" });
  });

  it("shows who wrote a note and when", async () => {
    serve(detail({ notes: [note({ mine: false })] }));
    await open();
    expect(screen.getByText("Omar, 2026-11-14")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Edit note" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete note" })).toBeNull();
  });

  it("the author can change a note", async () => {
    serve(detail({ notes: [note()] }));
    await open();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Edit note" }));
    const box = screen.getByLabelText("Edit note");
    await user.clear(box);
    await user.type(box, "Call on Tuesday");
    await user.click(screen.getByRole("button", { name: "Save note" }));
    await waitFor(() => expect(sent()).toHaveLength(1));
    expect(sent()[0][0]).toBe(`${URL}notes/n1/`);
    expect(sent()[0][1].method).toBe("PATCH");
    expect(JSON.parse(sent()[0][1].body)).toEqual({ text: "Call on Tuesday" });
  });

  it("the author can delete a note after a confirmation", async () => {
    serve(detail({ notes: [note()] }));
    await open();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete note" }));
    expect(sent()).toHaveLength(0);
    const dialog = await screen.findByRole("dialog", { name: "Delete note" });
    await user.click(within(dialog).getByRole("button", { name: "Delete note" }));
    await waitFor(() => expect(sent()).toHaveLength(1));
    expect(sent()[0][1].method).toBe("DELETE");
  });

  it("shows the field message when a note is refused", async () => {
    serve(detail());
    await open();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("New note"), "x");
    fetchMock.mockImplementation(async (_path: string, init?: { method?: string }) =>
      init?.method
        ? {
            ok: false,
            status: 400,
            json: async () => ({
              error: {
                code: "validation_error",
                message: "Check",
                fields: { text: "The note is too long." },
              },
            }),
          }
        : { ok: true, status: 200, json: async () => detail() },
    );
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The note is too long.");
  });
});
