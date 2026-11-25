import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CvUpload } from "./CvUpload";
import { RoleProvider } from "./role";

const getJson = vi.fn();
const uploadFiles = vi.fn();
vi.mock("@/lib/api", () => ({
  getJson: (...args: unknown[]) => getJson(...args),
  uploadFiles: (...args: unknown[]) => uploadFiles(...args),
}));

const RULES = {
  allowed_types: ["pdf", "docx"],
  max_file_size_mb: 10,
  max_files_per_batch: 3,
  max_files_in_progress: 5,
  files_in_progress: 0,
  blocked: null,
};
const pdf = (name = "a.pdf", size = 5) => new File([new Uint8Array(size)], name);
const accepted = (name: string) => ({
  ok: true,
  data: {
    results: [{ name, status: "accepted", code: "", message: "", prompt: null, notice: "" }],
  },
});
const refused = (name: string, message: string, prompt: string | null = null) => ({
  ok: true,
  data: { results: [{ name, status: "rejected", code: "x", message, prompt, notice: "" }] },
});

async function ready(role: "owner" | "member" = "owner") {
  render(
    <RoleProvider value={role}>
      <CvUpload projectId="p1" />
    </RoleProvider>,
  );
  await waitFor(() =>
    expect((screen.getByRole("button", { name: "Upload CVs" }) as HTMLButtonElement).disabled).toBe(
      false,
    ),
  );
}
const choose = (...files: File[]) =>
  userEvent.upload(screen.getByLabelText("Choose CV files"), files, { applyAccept: false });

beforeEach(() => {
  getJson.mockReset().mockResolvedValue({ ok: true, data: RULES });
  uploadFiles.mockReset();
});
afterEach(cleanup);

describe("CV upload", () => {
  it("reads the rules for the project", async () => {
    await ready();
    expect(getJson).toHaveBeenCalledWith("/api/company/projects/p1/cvs/");
    expect(screen.getByLabelText("Choose CV files").getAttribute("accept")).toBe(".pdf,.docx");
    expect((screen.getByLabelText("Choose CV files") as HTMLInputElement).multiple).toBe(true);
  });

  it("sends each file on its own and shows each result", async () => {
    uploadFiles.mockImplementation(async (_path, files: File[]) => accepted(files[0].name));
    await ready();
    await choose(pdf("a.pdf"), pdf("b.docx"));
    await waitFor(() => expect(screen.getAllByText("Added")).toHaveLength(2));
    expect(uploadFiles).toHaveBeenCalledTimes(2);
    expect(uploadFiles.mock.calls[0][0]).toBe("/api/company/projects/p1/cvs/");
    expect(uploadFiles.mock.calls.map((call) => (call[1] as File[]).length)).toEqual([1, 1]);
  });

  it("tells the page once, after all files are sent, that CVs are held for their estimate", async () => {
    const held = vi.fn();
    window.addEventListener("cvs-held", held);
    uploadFiles.mockImplementation(async (_path, files: File[]) => accepted(files[0].name));
    await ready();
    await choose(pdf("a.pdf"), pdf("b.pdf"));
    await waitFor(() => expect(screen.getAllByText("Added")).toHaveLength(2));
    window.removeEventListener("cvs-held", held);
    expect(held).toHaveBeenCalledTimes(1);
  });

  it("does not ask for an estimate when nothing was added", async () => {
    const held = vi.fn();
    window.addEventListener("cvs-held", held);
    uploadFiles.mockResolvedValue(refused("a.pdf", "Nope."));
    await ready();
    await choose(pdf("a.pdf"));
    await screen.findByText("Nope.");
    window.removeEventListener("cvs-held", held);
    expect(held).not.toHaveBeenCalled();
  });

  it("shows upload progress for a file", async () => {
    let finish: (value: unknown) => void = () => {};
    uploadFiles.mockImplementation(
      (_path, _files, onProgress: (fraction: number) => void) =>
        new Promise((resolve) => {
          onProgress(0.4);
          finish = resolve;
        }),
    );
    await ready();
    await choose(pdf());
    expect(await screen.findByText("Uploading 40%")).toBeTruthy();
    finish(accepted("a.pdf"));
    expect(await screen.findByText("Added")).toBeTruthy();
  });

  it("shows the notice for a CV with more pages than are read", async () => {
    uploadFiles.mockResolvedValue({
      ok: true,
      data: {
        results: [
          {
            name: "long.pdf",
            status: "accepted",
            code: "",
            message: "",
            prompt: null,
            notice: "This CV has 22 pages. Only the first 15 are read.",
          },
        ],
      },
    });
    await ready();
    await choose(pdf("long.pdf"));
    expect(
      await screen.findByText("Added. This CV has 22 pages. Only the first 15 are read."),
    ).toBeTruthy();
  });

  it("explains a wrong, empty or oversized file at once and still sends the good one", async () => {
    uploadFiles.mockImplementation(async (_path, files: File[]) => accepted(files[0].name));
    await ready();
    await choose(pdf("notes.txt"), pdf("empty.pdf", 0), pdf("good.pdf"));
    expect(await screen.findByText("Only PDF or DOCX files can be uploaded.")).toBeTruthy();
    expect(screen.getByText("This file is empty.")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Added")).toBeTruthy());
    expect(uploadFiles).toHaveBeenCalledTimes(1);
  });

  it("an oversized file is refused with the size from the rules", async () => {
    await ready();
    await choose(pdf("big.pdf", 10 * 1024 * 1024 + 1));
    expect(await screen.findByText("This file is larger than 10 MB.")).toBeTruthy();
    expect(uploadFiles).not.toHaveBeenCalled();
  });

  it("a drop over the batch size is refused as a whole and nothing is sent", async () => {
    await ready();
    await choose(pdf("1.pdf"), pdf("2.pdf"), pdf("3.pdf"), pdf("4.pdf"));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Only 3 files can be uploaded at a time. Nothing was added: choose fewer files.",
    );
    expect(uploadFiles).not.toHaveBeenCalled();
    expect(screen.queryByText("1.pdf")).toBeNull();
  });

  it("a drop that would pass the in-progress limit is refused as a whole", async () => {
    getJson.mockResolvedValue({ ok: true, data: { ...RULES, files_in_progress: 4 } });
    await ready();
    await choose(pdf("1.pdf"), pdf("2.pdf"));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "You already have 4 files waiting or being processed, and at most 5 are allowed at a time.",
    );
    expect(uploadFiles).not.toHaveBeenCalled();
  });

  it("the in-progress limit also counts what was sent since the page loaded", async () => {
    uploadFiles.mockImplementation(async (_path, files: File[]) => accepted(files[0].name));
    await ready();
    await choose(pdf("1.pdf"), pdf("2.pdf"), pdf("3.pdf"));
    await waitFor(() => expect(screen.getAllByText("Added")).toHaveLength(3));
    await choose(pdf("4.pdf"), pdf("5.pdf"), pdf("6.pdf"));
    expect((await screen.findByRole("alert")).textContent).toContain("You already have 3 files");
    expect(uploadFiles).toHaveBeenCalledTimes(3);
  });

  it("shows the server's message for a file it refuses", async () => {
    uploadFiles.mockResolvedValue(
      refused("a.pdf", "This file is password protected. Remove the password and upload it again."),
    );
    await ready();
    await choose(pdf());
    expect(
      await screen.findByText(
        "This file is password protected. Remove the password and upload it again.",
      ),
    ).toBeTruthy();
  });

  it("a reached CV limit opens the Upgrade popup", async () => {
    uploadFiles.mockResolvedValue(refused("a.pdf", "Limit reached.", "upgrade"));
    await ready();
    await choose(pdf());
    expect(await screen.findByText("Upgrade your plan")).toBeTruthy();
  });

  it("closing the popup keeps saying that uploads are blocked", async () => {
    uploadFiles.mockResolvedValue(refused("a.pdf", "Limit reached.", "upgrade"));
    await ready();
    await choose(pdf());
    await screen.findByText("Upgrade your plan");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Limit reached.");
    await userEvent.click(screen.getByRole("button", { name: "Show options" }));
    expect(await screen.findByText("Upgrade your plan")).toBeTruthy();
  });

  it("says it from the start when the server reports uploads as blocked", async () => {
    getJson.mockResolvedValue({
      ok: true,
      data: {
        ...RULES,
        blocked: {
          code: "subscription_expired",
          message: "Your subscription has ended.",
          prompt: "renewal",
        },
      },
    });
    await ready();
    expect(screen.getByRole("status").textContent).toContain("Your subscription has ended.");
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show options" }));
    expect(await screen.findByText("Renew your subscription")).toBeTruthy();
  });

  it("asks a member to pass it on instead of offering the button", async () => {
    uploadFiles.mockResolvedValue(refused("a.pdf", "Limit reached.", "upgrade"));
    await ready("member");
    await choose(pdf());
    expect(await screen.findByText("Please ask your company owner to upgrade.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Upgrade plan" })).toBeNull();
  });

  it("after a dropped connection only the failed file is sent again", async () => {
    uploadFiles
      .mockResolvedValueOnce(accepted("good.pdf"))
      .mockResolvedValueOnce({
        ok: false,
        error: { code: "unreachable", message: "We could not reach the server." },
      })
      .mockResolvedValueOnce(accepted("flaky.pdf"));
    await ready();
    await choose(pdf("good.pdf"), pdf("flaky.pdf"));
    await screen.findByText("We could not reach the server.");
    expect(screen.getAllByText("Added")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Try flaky.pdf again" }));
    await waitFor(() => expect(screen.getAllByText("Added")).toHaveLength(2));
    expect(uploadFiles).toHaveBeenCalledTimes(3);
    expect(((uploadFiles.mock.calls[2][1] as File[])[0] as File).name).toBe("flaky.pdf");
  });

  it("a file the server could not save can be tried again on its own", async () => {
    uploadFiles
      .mockResolvedValueOnce({
        ok: true,
        data: {
          results: [
            {
              name: "a.pdf",
              status: "failed",
              code: "storage_failed",
              message: "This file could not be saved. Please try again.",
              prompt: null,
              notice: "",
            },
          ],
        },
      })
      .mockResolvedValueOnce(accepted("a.pdf"));
    await ready();
    await choose(pdf("a.pdf"));
    expect(await screen.findByText("This file could not be saved. Please try again.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Try a.pdf again" }));
    expect(await screen.findByText("Added")).toBeTruthy();
    expect(uploadFiles).toHaveBeenCalledTimes(2);
  });

  it("a file already in the project is shown as skipped with the notice", async () => {
    uploadFiles.mockResolvedValue({
      ok: true,
      data: {
        results: [
          {
            name: "a.pdf",
            status: "skipped",
            code: "duplicate_file",
            message: "This file is already in the project, so it was skipped.",
            prompt: null,
            notice: "",
          },
        ],
      },
    });
    await ready();
    await choose(pdf("a.pdf"));
    expect(
      await screen.findByText("This file is already in the project, so it was skipped."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try a.pdf again" })).toBeNull();
  });

  it("everything chosen together shares one batch id, so it can be cancelled together", async () => {
    uploadFiles.mockImplementation(async (_path, files: File[]) => accepted(files[0].name));
    await ready();
    await choose(pdf("a.pdf"), pdf("b.pdf"));
    await waitFor(() => expect(uploadFiles).toHaveBeenCalledTimes(2));
    const batches = uploadFiles.mock.calls.map((call) => call[3].fields.batch);
    expect(batches[0]).toBeTruthy();
    expect(batches[0]).toBe(batches[1]);
    await choose(pdf("c.pdf"));
    await waitFor(() => expect(uploadFiles).toHaveBeenCalledTimes(3));
    expect(uploadFiles.mock.calls[2][3].fields.batch).not.toBe(batches[0]);
  });

  it("files can be dropped", async () => {
    uploadFiles.mockImplementation(async (_path, files: File[]) => accepted(files[0].name));
    await ready();
    fireEvent.drop(screen.getByTestId("cv-dropzone"), {
      dataTransfer: { files: [pdf("drop.pdf")] },
    });
    expect(await screen.findByText("Added")).toBeTruthy();
    expect(screen.getByText("drop.pdf")).toBeTruthy();
  });

  it("says plainly when the rules cannot be loaded", async () => {
    getJson.mockResolvedValue({ ok: false, error: { code: "not_found", message: "Not found." } });
    render(<CvUpload projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});
