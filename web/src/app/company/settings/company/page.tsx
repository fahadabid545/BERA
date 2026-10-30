import { Button, Input } from "@/components/ui";

export default function CompanySettingsPage() {
  return (
    <form className="page-form">
      <Input label="Company name" autoComplete="organization" />
      <div className="page-actions">
        <Button>Save</Button>
      </div>
    </form>
  );
}
