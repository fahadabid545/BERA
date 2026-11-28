import type { ReactNode } from "react";

import { Card } from "@/components/ui";

import type { Tint } from "./SceneTiles";

/** The sticker frame for the sign-in, sign-up, contact and token-link pages: a page heading and
 * the page's form or message on one tinted card. The title is the page's name, nothing more. */
export function AuthCard({
  title,
  tint = "lime",
  children,
}: {
  title: string;
  tint?: Tint;
  children: ReactNode;
}) {
  return (
    <>
      <header className="page-title-block">
        <h1 className="page-title">
          <span className="marker">{title}</span>
        </h1>
      </header>
      <Card className="auth-card" data-tint={tint}>
        {children}
      </Card>
    </>
  );
}
