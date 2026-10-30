import { ButtonLink } from "@/components/ui";

/** Shared by the website and both panels for unknown addresses. */
export function NotFoundMessage({ homeHref }: { homeHref: string }) {
  return (
    <div className="page-form">
      <h1>This page could not be found</h1>
      <div className="page-actions">
        <ButtonLink href={homeHref}>Go home</ButtonLink>
      </div>
    </div>
  );
}
