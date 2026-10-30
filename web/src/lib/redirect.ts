const DEFAULT_PAGE = "/company";

/**
 * Where to go after signing in: the page the person first asked for (`?next=`), but only
 * if it is a page of the company panel on this site. Anything else, such as another website
 * or a tricked-up address, goes to the dashboard instead.
 */
export function pageAfterLogin(requested: string | string[] | null | undefined): string {
  const value = Array.isArray(requested) ? requested[0] : requested;
  if (typeof value !== "string") return DEFAULT_PAGE;
  const isPanelPage = value === "/company" || /^\/company[/?#]/.test(value);
  const isTricky =
    /[\\\u0000-\u001f]/.test(value) ||
    value.startsWith("//") ||
    value.includes("://") ||
    value.split(/[/?#]/).includes("..");
  return isPanelPage && !isTricky ? value : DEFAULT_PAGE;
}
