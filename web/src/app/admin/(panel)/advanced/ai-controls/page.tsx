import { Button } from "@/components/ui";

export default function AiControlsPage() {
  return (
    <div className="page-actions">
      <Button variant="danger">Pause all AI</Button>
      <Button variant="secondary">Resume AI</Button>
      <Button>Save</Button>
    </div>
  );
}
