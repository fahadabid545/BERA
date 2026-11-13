import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CreateProjectForm } from "./CreateProjectForm";

const uploadFiles = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  uploadFiles: (...args: unknown[]) => uploadFiles(...args),
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn();

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({
    ok: status < 400,
    status,
    json: async () => body,
  });
}

function sentBodies() {
  return fetchMock.mock.calls.map((call) => JSON.parse(call[1].body as string));
}

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText("Project title"), "Backend engineer");
  await userEvent.type(screen.getByLabelText("Job description"), "Looks after servers");
  await userEvent.click(screen.getByRole("button", { name: "Create project" }));
}

beforeEach(() => {
  uploadFiles.mockReset();
  push.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("create project form", () => {
  it("shows the title, a large description box and both buttons", () => {
    render(<CreateProjectForm />);
    expect(screen.getByLabelText("Project title")).toBeTruthy();
    const description = screen.getByLabelText("Job description") as HTMLTextAreaElement;
    expect(description.tagName).toBe("TEXTAREA");
    expect(description.rows).toBeGreaterThan(5);
    expect(screen.getByRole("link", { name: "Cancel" }).getAttribute("href")).toBe(
      "/company/projects",
    );
  });

  it("has an optional job description file that takes PDF and Word files", () => {
    const { container } = render(<CreateProjectForm />);
    const picker = container.querySelector("input[type=file]") as HTMLInputElement;
    expect(picker.getAttribute("accept")).toBe(".pdf,.docx");
    expect(screen.getByLabelText("Job description file (optional)")).toBe(picker);
  });

  it("reads the chosen file on the server and puts its text in the description box", async () => {
    uploadFiles.mockResolvedValue({
      ok: true,
      data: { text: "Senior backend engineer needed", trimmed: false, notice: "" },
    });
    render(<CreateProjectForm />);
    const file = new File(["x"], "job.docx");
    await userEvent.upload(screen.getByLabelText("Job description file (optional)"), file);
    await waitFor(() =>
      expect((screen.getByLabelText("Job description") as HTMLTextAreaElement).value).toBe(
        "Senior backend engineer needed",
      ),
    );
    expect(uploadFiles.mock.calls[0][0]).toBe("/api/company/projects/read-description/");
    expect((uploadFiles.mock.calls[0][1] as File[])[0].name).toBe("job.docx");
  });

  it("the text from the file is what is sent when the project is created", async () => {
    uploadFiles.mockResolvedValue({
      ok: true,
      data: { text: "From the file", trimmed: false, notice: "" },
    });
    reply(201, { id: "abc" });
    render(<CreateProjectForm />);
    await userEvent.upload(
      screen.getByLabelText("Job description file (optional)"),
      new File(["x"], "job.pdf"),
    );
    await screen.findByDisplayValue("From the file");
    await userEvent.type(screen.getByLabelText("Project title"), "Backend engineer");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(sentBodies()[0].job_description).toBe("From the file");
  });

  it("a file the server cannot read shows its message next to the file and leaves the box alone", async () => {
    uploadFiles.mockResolvedValue({
      ok: false,
      error: {
        code: "validation_error",
        message: "Check.",
        fields: { file: "We could not read this file." },
      },
    });
    render(<CreateProjectForm />);
    await userEvent.type(screen.getByLabelText("Job description"), "typed by hand");
    await userEvent.upload(
      screen.getByLabelText("Job description file (optional)"),
      new File(["x"], "job.pdf"),
    );
    expect(await screen.findByText("We could not read this file.")).toBeTruthy();
    expect((screen.getByLabelText("Job description") as HTMLTextAreaElement).value).toBe(
      "typed by hand",
    );
  });

  it("says when the text was shortened to fit", async () => {
    uploadFiles.mockResolvedValue({
      ok: true,
      data: { text: "Long text", trimmed: true, notice: "" },
    });
    render(<CreateProjectForm />);
    await userEvent.upload(
      screen.getByLabelText("Job description file (optional)"),
      new File(["x"], "job.pdf"),
    );
    expect(await screen.findByText("The text was shortened to fit.")).toBeTruthy();
  });

  it("sends the text and goes to the projects list when created", async () => {
    reply(201, { id: "abc" });
    render(<CreateProjectForm />);
    await fillAndSubmit();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company/projects"));
    expect(sentBodies()[0]).toEqual({
      title: "Backend engineer",
      job_description: "Looks after servers",
      acknowledge_warnings: false,
    });
  });

  it("shows the server's field mistakes next to the fields", async () => {
    reply(400, {
      error: {
        code: "validation_error",
        message: "Check the form.",
        fields: { title: "This field may not be blank." },
      },
    });
    render(<CreateProjectForm />);
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByText("This field may not be blank.")).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  it("asks before creating when there are warnings, then sends again confirmed", async () => {
    reply(409, {
      error: {
        code: "project_warnings",
        message: "Please check the warnings.",
        details: {
          warnings: [
            { code: "short_description", message: "This description is under 300 characters." },
            { code: "duplicate_title", message: "You already have a project with this title." },
          ],
        },
      },
    });
    reply(201, { id: "abc" });
    render(<CreateProjectForm />);
    await fillAndSubmit();
    expect(await screen.findByText("This description is under 300 characters.")).toBeTruthy();
    expect(screen.getByText("You already have a project with this title.")).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Create anyway" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company/projects"));
    expect(sentBodies()[1].acknowledge_warnings).toBe(true);
    expect(sentBodies()[1].title).toBe("Backend engineer");
  });

  it("cancelling the warnings creates nothing", async () => {
    reply(409, {
      error: {
        code: "project_warnings",
        message: "x",
        details: { warnings: [{ code: "short_description", message: "Too short." }] },
      },
    });
    render(<CreateProjectForm />);
    await fillAndSubmit();
    await screen.findByText("Too short.");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(push).not.toHaveBeenCalled();
  });

  it("a reached project limit opens the Upgrade popup", async () => {
    reply(409, {
      error: {
        code: "project_limit_reached",
        message: "You have reached your plan's limit of 1 projects.",
        details: { limit: 1, prompt: "upgrade" },
      },
    });
    render(<CreateProjectForm />);
    await fillAndSubmit();
    expect(await screen.findByText("Upgrade your plan")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Upgrade plan" }).getAttribute("href")).toBe(
      "/company/billing",
    );
  });

  it("an ended subscription opens the Renewal popup", async () => {
    reply(409, {
      error: {
        code: "subscription_expired",
        message: "Your subscription has ended.",
        details: { limit: 1, prompt: "renewal" },
      },
    });
    render(<CreateProjectForm />);
    await fillAndSubmit();
    expect(await screen.findByText("Renew your subscription")).toBeTruthy();
  });

  it("another failure is shown in plain words", async () => {
    reply(500, { error: { code: "internal_error", message: "Something went wrong." } });
    render(<CreateProjectForm />);
    await fillAndSubmit();
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});
