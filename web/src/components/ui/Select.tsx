import type { SelectHTMLAttributes } from "react";

import { Field, type FieldProps } from "./Field";

export type SelectOption = { value: string; label: string };

export function Select({
  label,
  hint,
  error,
  options,
  ...props
}: FieldProps & { options: SelectOption[] } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(control) => (
        <div className={props.multiple ? "ui-select ui-select--multiple" : "ui-select"}>
          <select {...props} {...control}>
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}
    </Field>
  );
}
