"use client";

import { useState } from "react";

import { AnnouncementBanner } from "@/components/company/AnnouncementBanners";

/** The announcement banner as a company person sees it, with a working Dismiss. */
export function AnnouncementSample() {
  const [closed, setClosed] = useState(false);
  return closed ? (
    <p role="status">Dismissed.</p>
  ) : (
    <AnnouncementBanner message="Fake announcement text." onDismiss={() => setClosed(true)} />
  );
}
