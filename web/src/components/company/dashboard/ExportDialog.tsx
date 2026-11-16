import type { ReactNode } from "react";

import { ButtonLink, Dialog } from "@/components/ui";

/** Export report: the person picks the format here. The file opens in a spreadsheet; the page is
 * made to be printed or saved as a PDF from the browser. */
export function ExportDialog({
  days,
  trigger,
  area = "company",
}: {
  days: number;
  trigger: ReactNode;
  /** Whose report: the company's own or the whole platform's (admin). */
  area?: "company" | "admin";
}) {
  return (
    <Dialog trigger={trigger} title="Export report">
      <div className="export-choices">
        <a
          className="ui-button ui-button--primary"
          href={`/api/${area}/dashboard/report/?as=csv&days=${days}`}
          download
        >
          Download CSV file
        </a>
        <ButtonLink variant="secondary" href={`/${area}/dashboard/print?days=${days}`}>
          Open printable page
        </ButtonLink>
      </div>
    </Dialog>
  );
}
