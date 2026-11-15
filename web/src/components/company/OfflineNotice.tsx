"use client";

import { Tag } from "@/components/ui";
import { useOffline } from "@/lib/live";

/** Shown in the top bar while the live screens cannot reach the server. They catch up on their
 * own when the connection is back. */
export function OfflineNotice() {
  return useOffline() ? (
    <span role="status">
      <Tag variant="danger">Offline</Tag>
    </span>
  ) : null;
}
