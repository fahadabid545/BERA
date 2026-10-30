import { Button } from "@/components/ui";

export default function ProjectSettingsPage() {
  return (
    <div className="page-actions">
      <Button>Save</Button>
      <Button variant="secondary">Archive project</Button>
      <Button variant="danger">Delete project</Button>
    </div>
  );
}
