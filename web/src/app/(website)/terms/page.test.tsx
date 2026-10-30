import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import TermsPage from "./page";

describe("terms page", () => {
  it("has an empty body with no elements", () => {
    const { container } = render(<TermsPage />);
    expect(container.childElementCount).toBe(0);
  });
});
