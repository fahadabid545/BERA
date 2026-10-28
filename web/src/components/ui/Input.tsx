import type { InputHTMLAttributes } from "react";

import { Field, type FieldProps } from "./Field";

export function Input({
  label,
  hint,
  error,
  ...props
}: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(control) => <input className="ui-input" {...props} {...control} />}
    </Field>
  );
}
