import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "./page";

describe("privacy page", () => {
  it("has an empty body with no elements", () => {
    const { container } = render(<PrivacyPage />);
    expect(container.childElementCount).toBe(0);
  });
});
