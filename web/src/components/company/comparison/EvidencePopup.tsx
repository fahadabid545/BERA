import { ButtonLink, Dialog, Tag, TextLink } from "@/components/ui";

import { VerdictMark } from "./VerdictMark";
import { displayName, type Cell, type Compared, type Requirement } from "./types";

export type Evidence = { candidate: Compared; requirement: Requirement; cell: Cell };

/** What one result rests on: the requirement, the verdict, how sure the AI was and the words
 * from the CV that it based the verdict on, with a way on to the candidate. */
export function EvidencePopup({
  projectId,
  selection,
  onClose,
}: {
  projectId: string;
  selection: Evidence | null;
  onClose: () => void;
}) {
  const candidateHref = selection
    ? `/company/projects/${projectId}/candidates/${selection.candidate.id}`
    : "";
  return (
    <Dialog
      open={selection !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={selection ? displayName(selection.candidate) : ""}
      actions={
        selection && (
          <ButtonLink variant="secondary" href={candidateHref}>
            Open candidate
          </ButtonLink>
        )
      }
    >
      {selection && (
        <div className="evidence">
          <p>
            <TextLink href={`/company/projects/${projectId}/requirements`}>
              {selection.requirement.text}
            </TextLink>{" "}
            <Tag variant="neutral">
              {selection.requirement.kind === "must" ? "Must-have" : "Nice-to-have"}
            </Tag>
          </p>
          <p>
            <VerdictMark cell={selection.cell} />
            {selection.cell.confidence && (
              <span className="evidence__confidence"> {selection.cell.confidence} confidence</span>
            )}
          </p>
          {selection.cell.evidence ? (
            <blockquote className="evidence__quote">“{selection.cell.evidence}”</blockquote>
          ) : (
            <p role="status">No words from the CV are quoted for this result.</p>
          )}
        </div>
      )}
    </Dialog>
  );
}
