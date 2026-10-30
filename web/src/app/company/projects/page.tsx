import { NEW_PROJECT_HREF } from "@/components/company/links";
import { ButtonLink, Input } from "@/components/ui";

export default function ProjectsPage() {
  return (
    <div className="page-form">
      <Input label="Search" type="search" />
      <div className="page-actions">
        <ButtonLink href={NEW_PROJECT_HREF}>New project</ButtonLink>
      </div>
    </div>
  );
}
