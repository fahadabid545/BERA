import { Button, Input } from "@/components/ui";

export default function CompaniesPage() {
  return (
    <div className="page-form">
      <Input label="Search" type="search" />
      <div className="page-actions">
        <Button variant="secondary">Filters</Button>
      </div>
    </div>
  );
}
