import { Button } from "@/components/ui";

export default function SecurityPage() {
  return (
    <div className="page-actions">
      <Button>Set up two-step verification</Button>
      <Button variant="secondary">Sign out of all devices</Button>
    </div>
  );
}
