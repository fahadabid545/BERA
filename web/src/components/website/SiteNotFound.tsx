import { ButtonLink } from "@/components/ui";

/** The website's unknown-address page. The panels keep the calm NotFoundMessage. */
export function SiteNotFound({ homeHref }: { homeHref: string }) {
  return (
    <section className="site-not-found" aria-labelledby="site-not-found-title">
      <p className="site-not-found__code" aria-hidden="true">
        <span>4</span>
        <span className="site-not-found__zero">0</span>
        <span>4</span>
      </p>
      <h1 id="site-not-found-title" className="site-not-found__title">
        This page could not be found
      </h1>
      <div className="page-actions">
        <ButtonLink href={homeHref}>Go home</ButtonLink>
      </div>
    </section>
  );
}
