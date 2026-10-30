import { Button, Input, Select, Textarea } from "@/components/ui";

// The models are configured from the admin panel later, so the lists start empty.
export default function AiPlaygroundPage() {
  return (
    <form className="page-form">
      <Input label="CV file" type="file" />
      <Textarea label="Job description" rows={12} />
      <Select label="Reading model" options={[]} />
      <Select label="Scoring model" options={[]} />
      <div className="page-actions">
        <Button>Run test</Button>
      </div>
    </form>
  );
}
