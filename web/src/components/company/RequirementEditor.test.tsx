import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RequirementEditor } from "./RequirementEditor";

const fetchMock = vi.fn();
const BASE = "/api/company/projects/p1/requirements/";
const stored = (...texts: string[]) => ({
  requirements: texts.map((text, index) => ({
    id: `id-${index}`,
    kind: "must",
    text,
    weight: 3,
  })),
  warnings: [],
});

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const sent = (index = 1) => JSON.parse(fetchMock.mock.calls[index][1].body as string);
const texts = () =>
  screen.queryAllByLabelText(/^Requirement \d+$/).map((input) => (input as HTMLInputElement).value);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("requirement editor", () => {
  it("shows the stored requirements with type and weight", async () => {
    reply(200, stored("Python", "SQL"));
    render(<RequirementEditor projectId="p1" />);
    expect(await screen.findByDisplayValue("Python")).toBeTruthy();
    expect(texts()).toEqual(["Python", "SQL"]);
    expect((screen.getByLabelText("Weight 1") as HTMLSelectElement).value).toBe("3");
    expect((screen.getByLabelText("Type 1") as HTMLSelectElement).value).toBe("must");
  });

  it("adds a requirement and saves the whole list in order", async () => {
    reply(200, stored("Python"));
    reply(200, stored("Python", "Django"));
    render(<RequirementEditor projectId="p1" />);
    await screen.findByDisplayValue("Python");
    await userEvent.click(screen.getByRole("button", { name: "Add requirement" }));
    await userEvent.type(screen.getByLabelText("Requirement 2"), "Django");
    await userEvent.selectOptions(screen.getByLabelText("Type 2"), "nice");
    await userEvent.selectOptions(screen.getByLabelText("Weight 2"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Requirements saved")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(BASE);
    expect(sent().requirements).toEqual([
      { id: "id-0", kind: "must", text: "Python", weight: 3 },
      { kind: "nice", text: "Django", weight: 5 },
    ]);
    expect(sent().acknowledge_rescoring).toBe(false);
  });

  it("removes and reorders", async () => {
    reply(200, stored("A", "B", "C"));
    render(<RequirementEditor projectId="p1" />);
    await screen.findByDisplayValue("A");
    await userEvent.click(screen.getByRole("button", { name: "Move requirement 3 up" }));
    expect(texts()).toEqual(["A", "C", "B"]);
    await userEvent.click(screen.getByRole("button", { name: "Move requirement 1 down" }));
    expect(texts()).toEqual(["C", "A", "B"]);
    await userEvent.click(screen.getByRole("button", { name: "Remove requirement 2" }));
    expect(texts()).toEqual(["C", "B"]);
  });

  it("the first Up and the last Down are off", async () => {
    reply(200, stored("A", "B"));
    render(<RequirementEditor projectId="p1" />);
    await screen.findByDisplayValue("A");
    const off = (name: string) =>
      (screen.getByRole("button", { name }) as HTMLButtonElement).disabled;
    expect(off("Move requirement 1 up")).toBe(true);
    expect(off("Move requirement 2 down")).toBe(true);
    expect(off("Move requirement 1 down")).toBe(false);
  });

  it("flags near-duplicates after saving", async () => {
    reply(200, stored("Python"));
    reply(200, {
      ...stored("Python", "python"),
      warnings: [{ code: "near_duplicate", message: '"Python" and "python" look alike.' }],
    });
    render(<RequirementEditor projectId="p1" />);
    await screen.findByDisplayValue("Python");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText('"Python" and "python" look alike.')).toBeTruthy();
  });

  it("shows the server's mistake in plain words", async () => {
    reply(200, stored());
    reply(400, {
      error: {
        code: "validation_error",
        message: "Check.",
        fields: { requirements: "A project can have at most 30 requirements." },
      },
    });
    render(<RequirementEditor projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "A project can have at most 30 requirements.",
    );
  });

  it("after scoring, a change asks first with the count and cost, then saves", async () => {
    reply(200, stored("Python"));
    reply(409, {
      error: {
        code: "rescoring_needed",
        message: "Re-scoring needed",
        details: { cvs: 12, estimated_cost: "0.840000" },
      },
    });
    reply(200, stored("Python"));
    render(<RequirementEditor projectId="p1" />);
    await screen.findByDisplayValue("Python");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Re-scoring needed")).toBeTruthy();
    expect(screen.getByText("12 CVs will be scored again. Estimated cost: 0.840000.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(sent(2).acknowledge_rescoring).toBe(true);
  });

  it("suggestions are added to the editor, not saved", async () => {
    reply(200, stored("Python"));
    reply(200, {
      requirements: [{ kind: "nice", text: "Kubernetes" }],
      warnings: [],
      fallback: false,
      message: "",
    });
    render(<RequirementEditor projectId="p1" />);
    await screen.findByDisplayValue("Python");
    await userEvent.click(screen.getByRole("button", { name: "Suggest requirements" }));
    await userEvent.click(await screen.findByRole("button", { name: "Add to requirements" }));
    expect(texts()).toEqual(["Python", "Kubernetes"]);
    expect((screen.getByLabelText("Type 2") as HTMLSelectElement).value).toBe("nice");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
