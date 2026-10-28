import type { ReactNode } from "react";

import { SiteFrame } from "@/components/website/SiteFrame";

export default function WebsiteLayout({ children }: { children: ReactNode }) {
  return <SiteFrame>{children}</SiteFrame>;
}
