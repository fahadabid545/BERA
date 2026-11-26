import { Button } from "@/components/ui";

import { pagesOf, type Page } from "./types";

export function Pager({
  listing,
  onPage,
}: {
  listing: Page<unknown>;
  onPage: (page: number) => void;
}) {
  const pages = pagesOf(listing);
  if (pages <= 1) return null;
  return (
    <div className="page-actions">
      <Button
        variant="secondary"
        disabled={listing.page <= 1}
        onClick={() => onPage(listing.page - 1)}
      >
        Previous
      </Button>
      <span>
        Page {listing.page} of {pages}
      </span>
      <Button
        variant="secondary"
        disabled={listing.page >= pages}
        onClick={() => onPage(listing.page + 1)}
      >
        Next
      </Button>
    </div>
  );
}
