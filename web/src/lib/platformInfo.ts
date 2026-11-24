"use client";

import { useEffect, useState } from "react";

import { getJson } from "@/lib/api";

export type PlatformInfo = {
  app_name: string;
  support_email: string;
  maintenance: { enabled: boolean; message: string };
};

/** What every screen may know, signed in or not: the platform's name, where to get help, and
 * whether maintenance mode is on. Null until it has loaded, or when it could not be loaded: the
 * screens that use it then simply leave that part out. */
export function usePlatformInfo(): PlatformInfo | null {
  const [info, setInfo] = useState<PlatformInfo | null>(null);
  useEffect(() => {
    let current = true;
    void getJson<PlatformInfo>("/api/platform/").then((result) => {
      if (current && result.ok && result.data && typeof result.data === "object") {
        setInfo(result.data);
      }
    });
    return () => {
      current = false;
    };
  }, []);
  return info;
}
