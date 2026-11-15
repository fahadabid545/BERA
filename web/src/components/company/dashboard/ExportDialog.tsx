import type { ReactNode } from "react";

import { ButtonLink, Dialog } from "@/components/ui";

/** Export report: the person picks the format here. The file opens in a spreadsheet; the page is
 * made to be printed or saved as a PDF from the browser. */
export function ExportDialog({ days, trigger }: { days: number; trigger: ReactNode }) {
  return (
    <Dialog trigger={trigger} title="Export report">
      <div className="export-choices">
        <a
          className="ui-button ui-button--primary"
          href={`/api/company/dashboard/report/?as=csv&days=${days}`}
          download
        >
          Download CSV file
        </a>
        <ButtonLink variant="secondary" href={`/company/dashboard/print?days=${days}`}>
          Open printable page
        </ButtonLink>
      </div>
    </Dialog>
  );
}
