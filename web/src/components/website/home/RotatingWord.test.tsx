import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RotatingWord } from "./RotatingWord";

describe("RotatingWord", () => {
  it("tells screen readers every word once, in one calm line", () => {
    render(<RotatingWord words={["faster", "fairer", "smarter"]} />);
    expect(screen.getByText("faster, fairer, smarter").className).toBe("visually-hidden");
  });

  it("hides the moving words from assistive technology and repeats the first to loop smoothly", () => {
    const { container } = render(<RotatingWord words={["faster", "fairer", "smarter"]} />);
    expect(container.querySelector(".rotating-word")?.getAttribute("aria-hidden")).toBe("true");
    const words = [...container.querySelectorAll("em")].map((item) => item.textContent);
    expect(words).toEqual(["faster", "fairer", "smarter", "faster"]);
  });
});
