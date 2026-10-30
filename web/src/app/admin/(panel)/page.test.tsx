import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AdminDashboardPage from "./page";

describe("admin dashboard page", () => {
  it("has an empty body", () => {
    const { container } = render(<AdminDashboardPage />);
    expect(container.childElementCount).toBe(0);
  });
});
