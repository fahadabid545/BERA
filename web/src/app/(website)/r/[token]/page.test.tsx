import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SharedReportPage from "./page";

describe("shared report page", () => {
  it("has an empty body", () => {
    const { container } = render(<SharedReportPage />);
    expect(container.childElementCount).toBe(0);
  });
});
