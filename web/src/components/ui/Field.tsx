import { useId, type ReactNode } from "react";

import { ErrorIcon } from "./icons";

export type FieldProps = { label: string; hint?: string; error?: string };

export type FieldControlProps = {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
};

/** Label, hint and error text wired to one control for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
}: FieldProps & { children: (control: FieldControlProps) => ReactNode }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint && hintId, error && errorId].filter(Boolean).join(" ");

  return (
    <div className="ui-field">
      <label htmlFor={id} className="ui-label">
        {label}
      </label>
      {children({
        id,
        "aria-describedby": describedBy || undefined,
        "aria-invalid": error ? true : undefined,
      })}
      {hint && (
        <p id={hintId} className="ui-hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="ui-error">
          <ErrorIcon />
          <span>
            <span className="visually-hidden">Error: </span>
            {error}
          </span>
        </p>
      )}
    </div>
  );
}
