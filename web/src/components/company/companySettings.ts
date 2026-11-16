import { useEffect, useState } from "react";

import { getJson, patchJson, type ApiError } from "@/lib/api";

export type CompanySettings = {
  name: string;
  /** The billing country: shown, never changed here. */
  country: string;
  retention: {
    days: number;
    chosen: number | null;
    default_days: number;
    choices: number[];
  };
};

const URL = "/api/company/settings/";

/** The company's settings, and a way to change them. Owner only: others get the server's
 * refusal as `error`. */
export function useCompanySettings() {
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void getJson<CompanySettings>(URL).then((result) => {
      if (result.ok) setSettings(result.data);
      else setError(result.error);
    });
  }, []);

  async function save(changes: { name?: string; retention_days?: number | null }) {
    const result = await patchJson<CompanySettings>(URL, changes);
    if (result.ok) {
      setError(null);
      setSettings(result.data);
      setSaved(true);
    } else setError(result.error);
  }

  return { settings, error, saved, setSaved, save };
}
