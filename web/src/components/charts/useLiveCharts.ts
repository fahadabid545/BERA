"use client";

import { useEffect, useState } from "react";

import { getJson, type ApiError } from "@/lib/api";
import { startLive } from "@/lib/live";

/** The numbers of a chart page, kept up to date on the server's refresh delay. */
export function useLiveCharts<T extends { refresh_seconds: number }>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(
    () =>
      startLive(
        () => getJson<T>(path),
        (result) => {
          if (result.ok) {
            setData(result.data);
            setError(null);
          } else setError(result.error);
        },
      ),
    [path],
  );
  return { data, error };
}
