import { Button, Select, Textarea } from "@/components/ui";

const STAGES = ["New", "Shortlisted", "Interview", "Approved", "Rejected"];

export default function CandidatePage() {
  return (
    <div className="page-form">
      <div className="page-actions">
        <Button>Download CV</Button>
      </div>
      <Select label="Stage" options={STAGES.map((stage) => ({ value: stage, label: stage }))} />
      <Textarea label="Notes" />
    </div>
  );
}
