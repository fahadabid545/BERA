import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DownloadPackageView } from "./DownloadPackageView";

const fetchMock = vi.fn();
const answer = (over: object = {}) => ({
  id: "pk1",
  project_id: "p1",
  status: "ready",
  files: 3,
  size_bytes: 2097152,
  created_at: "2026-11-16T10:00:00Z",
  expires_at: "2026-11-17T10:00:00Z",
  refresh_seconds: 3,
  ...over,
});
function serve(body: object, status = 200) {
  fetchMock.mockImplementation(async () => ({
    ok: status === 200,
    status,
    json: async () => body,
  }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a download", () => {
  it("asks for the package it was opened for", async () => {
    serve(answer());
    render(<DownloadPackageView packageId="pk1" />);
    await screen.findByRole("status");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/company/downloads/pk1/");
  });

  it("offers the zip, with its size and how long it stays, when it is ready", async () => {
    serve(answer());
    render(<DownloadPackageView packageId="pk1" />);
    expect((await screen.findByRole("status")).textContent).toBe("Ready");
    const link = screen.getByRole("link", { name: "Download zip" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/api/company/downloads/pk1/file/");
    expect(screen.getByText("2.0 MB")).toBeTruthy();
    expect(screen.getByText("2026-11-17 10:00")).toBeTruthy();
  });

  it("shows no button while it is being prepared", async () => {
    serve(answer({ status: "preparing", size_bytes: null, expires_at: null }));
    render(<DownloadPackageView packageId="pk1" />);
    expect((await screen.findByRole("status")).textContent).toBe("Preparing");
    expect(screen.queryByRole("link", { name: "Download zip" })).toBeNull();
  });

  it.each([
    ["failed", "Failed"],
    ["expired", "Expired"],
  ])("a %s package shows its status and no button", async (status, words) => {
    serve(answer({ status }));
    render(<DownloadPackageView packageId="pk1" />);
    expect((await screen.findByRole("status")).textContent).toBe(words);
    expect(screen.queryByRole("link", { name: "Download zip" })).toBeNull();
  });

  it("leads back to the candidates", async () => {
    serve(answer());
    render(<DownloadPackageView packageId="pk1" />);
    const back = (await screen.findByRole("link", {
      name: "Back to candidates",
    })) as HTMLAnchorElement;
    expect(back.getAttribute("href")).toBe("/company/projects/p1/candidates");
  });

  it("shows the server's message when it is not found", async () => {
    serve({ error: { code: "not_found", message: "Not found." } }, 404);
    render(<DownloadPackageView packageId="other" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});
