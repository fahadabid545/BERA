import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loginAddressForHere, onUploadsAtRisk, sessionEnded, startUpload } from "./session";

const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({
  navigateTo: (address: string) => navigateTo(address),
  currentAddress: () => window.location.pathname + window.location.search,
}));

beforeEach(() => {
  navigateTo.mockClear();
  window.history.pushState({}, "", "/company/projects/abc?tab=2");
});
afterEach(() => onUploadsAtRisk(null));

describe("signing in again", () => {
  it("comes back to the same page, including its query", () => {
    expect(loginAddressForHere()).toBe("/login?next=%2Fcompany%2Fprojects%2Fabc%3Ftab%3D2");
  });

  it("leaves the admin area for the admin login", () => {
    window.history.pushState({}, "", "/admin/users");
    expect(loginAddressForHere()).toBe("/admin/login");
  });

  it("goes there at once when nothing is uploading", () => {
    sessionEnded();
    expect(navigateTo).toHaveBeenCalledWith("/login?next=%2Fcompany%2Fprojects%2Fabc%3Ftab%3D2");
  });
});

describe("uploads in progress", () => {
  it("warn instead of leaving the page", () => {
    const warn = vi.fn();
    onUploadsAtRisk(warn);
    const finish = startUpload();
    sessionEnded();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(navigateTo).not.toHaveBeenCalled();
    finish();
  });

  it("stop mattering once they have finished, even if finishing is reported twice", () => {
    onUploadsAtRisk(vi.fn());
    const first = startUpload();
    const second = startUpload();
    first();
    first();
    sessionEnded(); // the second is still running
    expect(navigateTo).not.toHaveBeenCalled();
    second();
    sessionEnded();
    expect(navigateTo).toHaveBeenCalledTimes(1);
  });

  it("leave the page if nothing is there to show the warning", () => {
    const finish = startUpload();
    sessionEnded();
    expect(navigateTo).toHaveBeenCalledTimes(1);
    finish();
  });
});
