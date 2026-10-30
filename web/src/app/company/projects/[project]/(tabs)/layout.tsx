import type { ReactNode } from "react";

import { projectTabs } from "@/components/company/links";
import { TabLinks } from "@/components/ui";

export default async function ProjectLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ project: string }>;
}) {
  const { project } = await params;
  return (
    <>
      <TabLinks label="Project" items={projectTabs(project)} />
      <div className="ui-tab-panel">{children}</div>
    </>
  );
}
