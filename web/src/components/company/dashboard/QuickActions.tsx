import Link from "next/link";
import type { ReactNode } from "react";

import { Card } from "@/components/ui";

import { ExportDialog } from "./ExportDialog";

function Tile({ colour, children }: { colour: string; children: ReactNode }) {
  return <span className={`quick-tile quick-tile--${colour}`}>{children}</span>;
}

/** The things done most often, each one click away. Upload and share go to the project shown
 * in the top candidates; the others do not depend on a project. */
export function QuickActions({ projectId, days }: { projectId: string | null; days: number }) {
  const project = projectId ? `/company/projects/${projectId}` : "/company/projects";
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Quick actions</h2>
      </div>
      <div className="quick-actions">
        <Link href={project} className="quick-link">
          <Tile colour="green">Upload CVs</Tile>
        </Link>
        <Link href="/company/projects/new" className="quick-link">
          <Tile colour="blue">New project</Tile>
        </Link>
        <Link href={`${project}/candidates`} className="quick-link">
          <Tile colour="violet">Share report</Tile>
        </Link>
        <ExportDialog
          days={days}
          trigger={
            <button type="button" className="quick-link">
              <Tile colour="amber">Export report</Tile>
            </button>
          }
        />
      </div>
    </Card>
  );
}
