import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AnnouncementBanners } from "./AnnouncementBanners";

const fetchMock = vi.fn();
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Announcement banners", () => {
  it("shows the banners in the order the server sends them", async () => {
    reply(200, {
      items: [
        { id: 2, message: "Fake newest" },
        { id: 1, message: "Fake oldest" },
      ],
    });
    render(<AnnouncementBanners />);
    await screen.findByText("Fake newest");
    expect(screen.getAllByRole("status").map((banner) => banner.textContent)).toEqual([
      "Fake newestDismiss",
      "Fake oldestDismiss",
    ]);
  });

  it("shows nothing when there are no banners", async () => {
    reply(200, { items: [] });
    const { container } = render(<AnnouncementBanners />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("shows a message as plain text, never as markup", async () => {
    reply(200, { items: [{ id: 1, message: "<b>Fake bold</b>" }] });
    const { container } = render(<AnnouncementBanners />);
    await screen.findByText("<b>Fake bold</b>");
    expect(container.querySelector("b")).toBeNull();
  });

  it("dismisses one banner and keeps the others", async () => {
    reply(200, {
      items: [
        { id: 2, message: "Fake newest" },
        { id: 1, message: "Fake oldest" },
      ],
    });
    render(<AnnouncementBanners />);
    await screen.findByText("Fake newest");
    reply(200, {});
    await userEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[0]);
    await waitFor(() => expect(screen.queryByText("Fake newest")).toBeNull());
    expect(screen.getByText("Fake oldest")).toBeTruthy();
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe("/api/company/announcements/2/dismiss/");
    expect(init.method).toBe("POST");
  });

  it("keeps the banner and says why when it cannot be dismissed", async () => {
    reply(200, { items: [{ id: 1, message: "Fake notice" }] });
    render(<AnnouncementBanners />);
    await screen.findByText("Fake notice");
    reply(404, { error: { code: "not_found", message: "Not found." } });
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
    expect(screen.getByText("Fake notice")).toBeTruthy();
  });
});
