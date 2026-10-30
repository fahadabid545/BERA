import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FaqPage from "./page";

describe("faq page", () => {
  it("has no elements", () => {
    const { container } = render(<FaqPage />);
    expect(container.childElementCount).toBe(0);
  });
});
