import type { ReactNode } from "react";

import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

/** The shared frame of every public page: header, an empty content area, footer. */
export function SiteFrame({ children }: { children: ReactNode }) {
  return (
    <div className="site-frame">
      <SiteHeader />
      <main className="site-main">{children}</main>
      <SiteFooter />
    </div>
  );
}
