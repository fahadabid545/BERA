import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Reveal } from "./Reveal";

afterEach(() => vi.unstubAllGlobals());

function stubObserver() {
  let notify: (entries: { isIntersecting: boolean }[]) => void = () => {};
  const disconnect = vi.fn();
  class FakeObserver {
    constructor(callback: typeof notify) {
      notify = callback;
    }
    observe = vi.fn();
    disconnect = disconnect;
  }
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  return {
    notify: (visible: boolean) => act(() => notify([{ isIntersecting: visible }])),
    disconnect,
  };
}

describe("Reveal", () => {
  it("shows its content at once where scroll observers are missing", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(<Reveal>Content</Reveal>);
    expect(screen.getByText("Content").getAttribute("data-reveal")).toBe("visible");
  });

  it("shows its content at once with reduced motion", () => {
    stubObserver();
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    render(<Reveal>Content</Reveal>);
    expect(screen.getByText("Content").getAttribute("data-reveal")).toBe("visible");
  });

  it("waits off screen, then shows once, when it scrolls into view", () => {
    const observer = stubObserver();
    render(<Reveal>Content</Reveal>);
    const element = screen.getByText("Content");
    expect(element.getAttribute("data-reveal")).toBe("waiting");

    observer.notify(false);
    expect(element.getAttribute("data-reveal")).toBe("waiting");

    observer.notify(true);
    expect(element.getAttribute("data-reveal")).toBe("shown");
    expect(observer.disconnect).toHaveBeenCalled();
  });

  it("renders the element and classes it is given", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(
      <Reveal as="p" className="extra">
        Label
      </Reveal>,
    );
    const element = screen.getByText("Label");
    expect(element.tagName).toBe("P");
    expect(element.className).toBe("reveal extra");
  });
});
