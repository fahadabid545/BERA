import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PrivacyPage from "@/app/(website)/privacy/page";
import TermsPage from "@/app/(website)/terms/page";

function serve(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}
const EMPTY = {
  terms: { title: "Terms", sections: [] },
  privacy: { title: "Privacy", sections: [] },
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("legal pages with no text yet", () => {
  it("terms says it is being prepared and holds no legal wording", async () => {
    serve(EMPTY);
    const { container } = render(<TermsPage />);
    expect(await screen.findByText("This page is being prepared")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Terms");
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("privacy says it is being prepared", async () => {
    serve(EMPTY);
    render(<PrivacyPage />);
    expect(await screen.findByText("This page is being prepared")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Privacy");
  });
});

describe("legal pages with text", () => {
  const filled = {
    ...EMPTY,
    terms: {
      title: "Terms",
      sections: [{ heading: "Fake heading", paragraphs: ["Fake one.", "Fake two."] }],
    },
  };

  it("show the text exactly as supplied, and no longer the preparing line", async () => {
    serve(filled);
    render(<TermsPage />);
    expect(await screen.findByRole("heading", { name: "Fake heading" })).toBeTruthy();
    expect(screen.getByText("Fake one.")).toBeTruthy();
    expect(screen.getByText("Fake two.")).toBeTruthy();
    expect(screen.queryByText("This page is being prepared")).toBeNull();
  });

  it("never show whether the text was reviewed", async () => {
    serve(filled);
    const { container } = render(<TermsPage />);
    await screen.findByText("Fake one.");
    expect(container.textContent).not.toMatch(/review|draft/i);
  });
});

describe("when the text cannot be loaded", () => {
  it("says so in plain words", async () => {
    serve({ error: { code: "x", message: "Something went wrong." } }, 500);
    render(<TermsPage />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});
