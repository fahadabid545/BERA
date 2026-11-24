"use client";

import { usePlatformInfo } from "@/lib/platformInfo";

export function NoAccess() {
  const info = usePlatformInfo();
  return (
    <>
      <h1>You do not have access</h1>
      {info?.support_email && <p>Contact {info.support_email}.</p>}
    </>
  );
}
