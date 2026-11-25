import type { MetadataRoute } from "next";

import { PUBLIC_PAGES, siteUrl } from "@/lib/seo";

/** The public pages only. No dates: nothing here is invented. */
export default function sitemap(): MetadataRoute.Sitemap {
  const address = siteUrl();
  return Object.values(PUBLIC_PAGES).map((page) => ({ url: `${address}${page.path}` }));
}
