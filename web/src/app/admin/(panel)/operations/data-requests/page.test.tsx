import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DataRequestsPage from "./page";

describe("Data requests page", () => {
  it("has an empty body", () => {
    const { container } = render(<DataRequestsPage />);
    expect(container.childElementCount).toBe(0);
  });
});
