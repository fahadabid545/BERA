/** The hiring stages, in order, as the server names them. */
export const STAGES = [
  { value: "new", label: "New" },
  { value: "shortlisted", label: "Shortlisted" },
  { value: "interview", label: "Interview" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

export const stageLabel = (value: string | null) =>
  STAGES.find((stage) => stage.value === value)?.label ?? value ?? "";
