import { Button, Select } from "@/components/ui";

const RETENTION_DAYS = [30, 90, 180, 365];

export default function RetentionPage() {
  return (
    <form className="page-form">
      <Select
        label="Retention"
        options={RETENTION_DAYS.map((days) => ({ value: String(days), label: `${days} days` }))}
      />
      <div className="page-actions">
        <Button>Save</Button>
      </div>
    </form>
  );
}
