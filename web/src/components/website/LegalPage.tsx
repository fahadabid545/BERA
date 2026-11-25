"use client";

import { useEffect, useState } from "react";

import { LEGAL_PREPARING } from "@/components/website/content";
import { getJson } from "@/lib/api";

type LegalDocument = { title: string; sections: { heading: string; paragraphs: string[] }[] };

/** A legal page (Terms or Privacy). The wording comes from the server, supplied by the owner after
 * legal review; with no text yet the page says so. It never shows whether the text was reviewed. */
export function LegalPage({ document }: { document: "terms" | "privacy" }) {
  const [text, setText] = useState<LegalDocument | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    getJson<Record<string, LegalDocument>>("/api/legal/").then((result) => {
      if (result.ok) setText(result.data[document]);
      else setProblem(result.error.message);
    });
  }, [document]);

  if (problem) return <p role="alert">{problem}</p>;
  if (!text) return null;
  return (
    <div className="page-stack">
      <h1>{text.title}</h1>
      {text.sections.length === 0 && <p>{LEGAL_PREPARING}</p>}
      {text.sections.map((section) => (
        <section key={section.heading}>
          <h2>{section.heading}</h2>
          {section.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </section>
      ))}
    </div>
  );
}
