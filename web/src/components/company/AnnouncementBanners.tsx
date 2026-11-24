"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";

type Banner = { id: number; message: string };

const BASE = "/api/company/announcements/";

/** One banner. Its words come from an admin and are shown as plain text. */
export function AnnouncementBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return (
    <div className="announcement" role="status">
      <p>{message}</p>
      <Button variant="secondary" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  );
}

/** The admins' notices that are on now for this person's company, newest first. Closing one hides
 * it for this person only. Expired ones never come back from the server. */
export function AnnouncementBanners() {
  const [banners, setBanners] = useState<Banner[]>([]);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let current = true;
    void getJson<{ items: Banner[] }>(BASE).then((result) => {
      if (!current) return;
      if (result.ok) setBanners(result.data.items);
      else setError(result.error);
    });
    return () => {
      current = false;
    };
  }, []);

  async function dismiss(banner: Banner) {
    setError(null);
    const result = await postJson(`${BASE}${banner.id}/dismiss/`, {});
    if (result.ok) setBanners((all) => all.filter((each) => each.id !== banner.id));
    else setError(result.error);
  }

  if (banners.length === 0 && !error) return null;
  return (
    <div className="announcements">
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      {banners.map((banner) => (
        <AnnouncementBanner
          key={banner.id}
          message={banner.message}
          onDismiss={() => void dismiss(banner)}
        />
      ))}
    </div>
  );
}
