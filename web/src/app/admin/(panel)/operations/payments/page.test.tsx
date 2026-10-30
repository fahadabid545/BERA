import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PaymentsPage from "./page";

describe("Payments page", () => {
  it("has an empty body", () => {
    const { container } = render(<PaymentsPage />);
    expect(container.childElementCount).toBe(0);
  });
});
