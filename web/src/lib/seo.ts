import { existsSync } from "node:fs";
import path from "node:path";

import type { Metadata } from "next";

import { readSiteUrl } from "@/lib/siteUrl";

/** One row per public page: its address and its approved title and description. The platform's
 * name is written as {app} and filled from the app name setting, never typed here. */
export const PUBLIC_PAGES = {
  home: {
    path: "/",
    title: "{app}",
    description:
      "Upload CVs in bulk. {app} scores each one against your job requirements and ranks the best candidates.",
  },
  features: {
    path: "/features",
    title: "Features | {app}",
    description: "Job projects, bulk CV upload, AI scoring, ranked comparison and more.",
  },
  howItWorks: {
    path: "/how-it-works",
    title: "How it works | {app}",
    description: "Create a project, upload CVs, get scores, then compare and decide.",
  },
  pricing: {
    path: "/pricing",
    title: "Pricing | {app}",
    description: "Plans and prices for {app}.",
  },
  faq: {
    path: "/faq",
    title: "FAQ | {app}",
    description: "Short answers to common questions.",
  },
  contact: {
    path: "/contact",
    title: "Contact | {app}",
    description: "Get in touch with the {app} team.",
  },
  terms: {
    path: "/terms",
    title: "Terms | {app}",
    description: "Terms of use for {app}.",
  },
  privacy: {
    path: "/privacy",
    title: "Privacy | {app}",
    description: "Privacy policy for {app}.",
  },
  login: {
    path: "/login",
    title: "Log in | {app}",
    description: "Log in to your {app} account.",
  },
  signup: {
    path: "/signup",
    title: "Sign up | {app}",
    description: "Create your {app} account.",
  },
} as const;

export type PublicPage = keyof typeof PUBLIC_PAGES;

// Used only when the server cannot be reached while the page is built.
const NAME_WHEN_UNAVAILABLE = "Bera";
const NAME_CACHE_SECONDS = 300;
const COVER_PATH = "/og-cover.png";
const COVER_WIDTH = 1200;
const COVER_HEIGHT = 630;

export const siteUrl = () => readSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);

/** The platform's name from the app name setting. */
export async function appName(): Promise<string> {
  const server = process.env.API_URL ?? "http://127.0.0.1:8000";
  try {
    const reply = await fetch(`${server}/api/platform/`, {
      next: { revalidate: NAME_CACHE_SECONDS },
    });
    const name = reply.ok ? ((await reply.json()) as { app_name?: unknown }).app_name : null;
    return typeof name === "string" && name ? name : NAME_WHEN_UNAVAILABLE;
  } catch {
    return NAME_WHEN_UNAVAILABLE;
  }
}

/** The sharing preview is offered only when the cover file exists, so a link never points at a
 * missing image. */
export const coverExists = () => existsSync(path.join(process.cwd(), "public", COVER_PATH));

export function buildMetadata(
  page: PublicPage,
  { app, address, hasCover }: { app: string; address: string; hasCover: boolean },
): Metadata {
  const entry = PUBLIC_PAGES[page];
  const title = entry.title.replaceAll("{app}", app);
  const description = entry.description.replaceAll("{app}", app);
  const url = `${address}${entry.path}`;
  const images = hasCover
    ? [{ url: COVER_PATH, width: COVER_WIDTH, height: COVER_HEIGHT, alt: app }]
    : undefined;
  return {
    metadataBase: new URL(address),
    title,
    description,
    alternates: { canonical: url },
    openGraph: { type: "website", siteName: app, title, description, url, images },
    twitter: {
      card: hasCover ? "summary_large_image" : "summary",
      title,
      description,
      images: hasCover ? [COVER_PATH] : undefined,
    },
  };
}

export async function pageMetadata(page: PublicPage): Promise<Metadata> {
  return buildMetadata(page, {
    app: await appName(),
    address: siteUrl(),
    hasCover: coverExists(),
  });
}

/** For pages search engines must not list. The headers in the middleware say the same. */
export const privatePage: Metadata = { robots: { index: false, follow: false } };
/** For pages reached from a link that holds a one-time secret: also never sent on as a referrer. */
export const tokenLinkPage: Metadata = { ...privatePage, referrer: "no-referrer" };
