import { Button } from "@/components/ui";

export default function CompanyDetailPage() {
  return (
    <div className="page-actions">
      <Button variant="danger">Suspend</Button>
      <Button variant="danger">Terminate subscription</Button>
      <Button variant="secondary">Grant free subscription</Button>
      <Button variant="secondary">Change limits</Button>
      <Button variant="danger">Block member</Button>
    </div>
  );
}
