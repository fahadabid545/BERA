"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";

import { Dialog, Select, Textarea } from "@/components/ui";
import { postJson, type ApiError } from "@/lib/api";

type Kind = "bug" | "idea" | "question";

const URL = "/api/company/feedback/";
const KIND_WORDS: Record<Kind, string> = { bug: "Bug", idea: "Idea", question: "Question" };
const KINDS = Object.keys(KIND_WORDS) as Kind[];

/** "Send feedback": a kind and a message. The page it was sent from is added here, never typed.
 * The popup closes when confirmed; a refused message comes back with what was typed. */
export function FeedbackDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const pathname = usePathname();
  const [kind, setKind] = useState<Kind>("bug");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState(false);

  async function send() {
    setError(null);
    const result = await postJson(URL, { kind, message, page: pathname });
    if (result.ok) {
      setMessage("");
      setSent(true);
      return;
    }
    setError(result.error);
    onOpenChange(true);
  }

  const fields = error?.fields ?? {};
  const alertText = error && Object.keys(fields).length === 0 ? error.message : null;
  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
        title="Send feedback"
        confirmLabel="Send"
        onConfirm={() => void send()}
      >
        <div className="page-stack">
          {alertText && (
            <p className="ui-error" role="alert">
              {alertText}
            </p>
          )}
          <Select
            label="Kind"
            value={kind}
            error={fields.kind}
            onChange={(event) => setKind(event.target.value as Kind)}
            options={KINDS.map((each) => ({ value: each, label: KIND_WORDS[each] }))}
          />
          <Textarea
            label="Message"
            value={message}
            error={fields.message ?? fields.page}
            onChange={(event) => setMessage(event.target.value)}
          />
        </div>
      </Dialog>
      <Dialog open={sent} onOpenChange={setSent} title="Feedback sent" />
    </>
  );
}
