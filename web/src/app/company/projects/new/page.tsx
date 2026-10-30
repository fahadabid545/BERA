import { PROJECTS_HREF } from "@/components/company/links";
import { Button, ButtonLink, Input, Textarea } from "@/components/ui";

export default function NewProjectPage() {
  return (
    <form className="page-form">
      <Input label="Project title" />
      <Textarea label="Job description" rows={12} />
      <div className="page-actions">
        <Button>Create project</Button>
        <ButtonLink href={PROJECTS_HREF} variant="secondary">
          Cancel
        </ButtonLink>
      </div>
    </form>
  );
}
