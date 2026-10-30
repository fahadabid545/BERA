import type { TextareaHTMLAttributes } from "react";

import { Field, type FieldProps } from "./Field";

export function Textarea({
  label,
  hint,
  error,
  ...props
}: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(control) => <textarea className="ui-input ui-textarea" rows={5} {...props} {...control} />}
    </Field>
  );
}
