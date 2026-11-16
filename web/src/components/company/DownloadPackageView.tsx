"use client";

import { useEffect, useState } from "react";

import { Card, TextLink } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";
import { startLive } from "@/lib/live";

import type { DownloadPackage } from "./downloads";

const STATUSES = {
  preparing: "Preparing",
  ready: "Ready",
  failed: "Failed",
  expired: "Expired",
};
const MEGABYTE = 1024 * 1024;
const DATE_LENGTH = 16;

/** One zip of CVs: its state, looked at again while it is being made, and the button to save it
 * once it is ready. The file is fetched through the signed-in session each time. */
export function DownloadPackageView({ packageId }: { packageId: string }) {
  const [shown, setShown] = useState<DownloadPackage | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(
    () =>
      startLive(
        () => getJson<DownloadPackage>(`/api/company/downloads/${packageId}/`),
        (result) => {
          if (result.ok) setShown(result.data);
          else setError(result.error);
        },
      ),
    [packageId],
  );

  if (error) {
    return (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    );
  }
  if (!shown) return null;
  return (
    <Card>
      <h1>Download</h1>
      <dl className="usage-details">
        <dt>Status</dt>
        <dd role="status">{STATUSES[shown.status]}</dd>
        <dt>CVs</dt>
        <dd>{shown.files}</dd>
        {shown.size_bytes !== null && (
          <>
            <dt>Size</dt>
            <dd>{(shown.size_bytes / MEGABYTE).toFixed(1)} MB</dd>
          </>
        )}
        {shown.expires_at && (
          <>
            <dt>Available until</dt>
            <dd>{shown.expires_at.slice(0, DATE_LENGTH).replace("T", " ")}</dd>
          </>
        )}
      </dl>
      {shown.status === "ready" && (
        <a
          className="ui-button ui-button--primary"
          href={`/api/company/downloads/${packageId}/file/`}
          download
        >
          Download zip
        </a>
      )}
      <TextLink href={`/company/projects/${shown.project_id}/candidates`}>
        Back to candidates
      </TextLink>
    </Card>
  );
}
