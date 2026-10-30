import type { InputHTMLAttributes, ReactNode } from "react";

export function Checkbox({
  label,
  ...props
}: { label: ReactNode } & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  return (
    <label className="ui-checkbox">
      <input type="checkbox" {...props} />
      <span>{label}</span>
    </label>
  );
}
