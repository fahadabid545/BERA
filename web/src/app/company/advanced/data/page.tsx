import { Button } from "@/components/ui";

export default function DataPage() {
  return (
    <div className="page-actions">
      <Button variant="secondary">Export data</Button>
      <Button variant="danger">Delete company</Button>
    </div>
  );
}
