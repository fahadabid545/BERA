/** The hiring stages, in order, as the server names them. */
export const STAGES = [
  { value: "new", label: "New" },
  { value: "shortlisted", label: "Shortlisted" },
  { value: "interviewed", label: "Interviewed" },
  { value: "on_hold", label: "On hold" },
  { value: "selected", label: "Selected" },
  { value: "rejected", label: "Rejected" },
];

export const stageLabel = (value: string | null) =>
  STAGES.find((stage) => stage.value === value)?.label ?? value ?? "";
