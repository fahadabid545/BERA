const DEVELOPMENT_ADDRESS = "http://localhost:3000";

/** The website's public address, used only to write the sitemap, canonical and sharing links. It
 * is never used to decide anything about security (no redirects, no allowed origins).
 * Production needs an https address with no path and no trailing slash; development may leave it
 * out. Anything else stops the app so a wrong address never reaches search engines. */
export function readSiteUrl(
  value: string | undefined,
  environment: string | undefined = process.env.NODE_ENV,
): string {
  const production = environment === "production";
  if (!value) {
    if (production) throw new Error("NEXT_PUBLIC_SITE_URL must be set in production.");
    return DEVELOPMENT_ADDRESS;
  }
  let address: URL;
  try {
    address = new URL(value);
  } catch {
    throw new Error("NEXT_PUBLIC_SITE_URL must be a full web address.");
  }
  const clean =
    address.pathname === "/" &&
    !address.search &&
    !address.hash &&
    !address.username &&
    !value.endsWith("/");
  if (!clean) {
    throw new Error(
      "NEXT_PUBLIC_SITE_URL must be only the address, with no path, query or trailing slash.",
    );
  }
  if (production && address.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_SITE_URL must start with https:// in production.");
  }
  if (address.protocol !== "https:" && address.protocol !== "http:") {
    throw new Error("NEXT_PUBLIC_SITE_URL must be an http or https address.");
  }
  return value;
}
