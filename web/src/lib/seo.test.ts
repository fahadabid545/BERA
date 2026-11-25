import { afterEach, describe, expect, it, vi } from "vitest";

import { buildMetadata, PUBLIC_PAGES, type PublicPage, appName } from "./seo";

const ADDRESS = "https://bera.example.com";
const meta = (page: PublicPage, hasCover = true, app = "Fake App") =>
  buildMetadata(page, { app, address: ADDRESS, hasCover });

afterEach(() => vi.unstubAllGlobals());

const APPROVED: Record<PublicPage, [string, string]> = {
  home: [
    "Fake App",
    "Upload CVs in bulk. Fake App scores each one against your job requirements and ranks the best candidates.",
  ],
  features: [
    "Features | Fake App",
    "Job projects, bulk CV upload, AI scoring, ranked comparison and more.",
  ],
  howItWorks: [
    "How it works | Fake App",
    "Create a project, upload CVs, get scores, then compare and decide.",
  ],
  pricing: ["Pricing | Fake App", "Plans and prices for Fake App."],
  faq: ["FAQ | Fake App", "Short answers to common questions."],
  contact: ["Contact | Fake App", "Get in touch with the Fake App team."],
  terms: ["Terms | Fake App", "Terms of use for Fake App."],
  privacy: ["Privacy | Fake App", "Privacy policy for Fake App."],
  login: ["Log in | Fake App", "Log in to your Fake App account."],
  signup: ["Sign up | Fake App", "Create your Fake App account."],
};

describe("titles and descriptions", () => {
  it.each(Object.keys(APPROVED) as PublicPage[])("%s uses the approved wording", (page) => {
    const result = meta(page);
    expect([result.title, result.description]).toEqual(APPROVED[page]);
  });

  it("covers every public page and writes the name from the setting, never in the table", () => {
    expect(Object.keys(PUBLIC_PAGES).sort()).toEqual(Object.keys(APPROVED).sort());
    expect(JSON.stringify(PUBLIC_PAGES)).not.toMatch(/Bera/);
  });
});

describe("sharing preview", () => {
  it("repeats the title and description and points at the cover when it exists", () => {
    const result = meta("features");
    expect(result.openGraph).toMatchObject({
      title: "Features | Fake App",
      description: APPROVED.features[1],
      url: `${ADDRESS}/features`,
      siteName: "Fake App",
      images: [{ url: "/og-cover.png", width: 1200, height: 630, alt: "Fake App" }],
    });
    expect(result.twitter).toMatchObject({
      card: "summary_large_image",
      images: ["/og-cover.png"],
    });
  });

  it("has no image link at all while the cover file is missing", () => {
    const result = meta("features", false);
    expect(result.openGraph).toMatchObject({ images: undefined });
    expect(result.twitter).toMatchObject({ card: "summary", images: undefined });
  });

  it("gives every page its own canonical address", () => {
    expect(meta("home").alternates?.canonical).toBe(`${ADDRESS}/`);
    expect(meta("howItWorks").alternates?.canonical).toBe(`${ADDRESS}/how-it-works`);
  });
});

describe("the app name", () => {
  it("is read from the platform setting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ app_name: "Fake App" }))),
    );
    expect(await appName()).toBe("Fake App");
  });

  it("falls back when the server cannot be reached or answers badly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new Error("down"))),
    );
    expect(await appName()).toBe("Bera");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 500 })),
    );
    expect(await appName()).toBe("Bera");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ app_name: 5 }))),
    );
    expect(await appName()).toBe("Bera");
  });
});
