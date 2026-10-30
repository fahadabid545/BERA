export const PROJECTS_HREF = "/company/projects";
export const NEW_PROJECT_HREF = `${PROJECTS_HREF}/new`;

export function projectTabs(project: string) {
  const base = `${PROJECTS_HREF}/${project}`;
  return [
    { label: "Overview", href: base, exact: true },
    { label: "Candidates", href: `${base}/candidates` },
    { label: "Compare", href: `${base}/compare` },
    { label: "Requirements", href: `${base}/requirements` },
    { label: "Settings", href: `${base}/settings` },
  ];
}
