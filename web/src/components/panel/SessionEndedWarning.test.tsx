import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { sessionEnded, startUpload } from "@/lib/session";

import { SessionEndedWarning } from "./SessionEndedWarning";

const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({
  navigateTo: (address: string) => navigateTo(address),
  currentAddress: () => window.location.pathname + window.location.search,
}));

beforeEach(() => {
  navigateTo.mockClear();
  window.history.pushState({}, "", "/company/projects/abc");
});

describe("the warning about a session that ended during an upload", () => {
  it("is not shown until a session ends while files are uploading", () => {
    render(<SessionEndedWarning />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("warns, and Log in returns to the same page afterwards", async () => {
    render(<SessionEndedWarning />);
    const finish = startUpload();
    act(() => sessionEnded());
    const popup = await screen.findByRole("dialog");
    expect(popup.textContent).toContain("Files that are still uploading may be lost");
    expect(navigateTo).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(navigateTo).toHaveBeenCalledWith("/login?next=%2Fcompany%2Fprojects%2Fabc");
    finish();
  });

  it("can be closed to stay on the page", async () => {
    render(<SessionEndedWarning />);
    const finish = startUpload();
    act(() => sessionEnded());
    await userEvent.click(await screen.findByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(navigateTo).not.toHaveBeenCalled();
    finish();
  });

  it("stops listening when it goes away, so a later end of session leaves the page", () => {
    const { unmount } = render(<SessionEndedWarning />);
    unmount();
    const finish = startUpload();
    sessionEnded();
    expect(navigateTo).toHaveBeenCalledTimes(1);
    finish();
  });
});
