import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/seo";

/** Private pages are kept out of search results by noindex (see the middleware), not by listing
 * them here: a list of private paths would publish their addresses. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${siteUrl()}/sitemap.xml`,
  };
}
