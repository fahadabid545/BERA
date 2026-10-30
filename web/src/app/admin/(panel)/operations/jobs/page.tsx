import { Button } from "@/components/ui";

export default function JobsPage() {
  return (
    <div className="page-actions">
      <Button>Retry</Button>
      <Button variant="secondary">Cancel job</Button>
    </div>
  );
}
