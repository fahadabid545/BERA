"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { getJson, type ApiError } from "@/lib/api";

import { CompanyFrame } from "./CompanyFrame";
import type { CompanyRole } from "./navigation";

type Me = { name: string; company_name: string; role: CompanyRole };

/**
 * The company area for the person who is signed in. The name, company and role come from the
 * server and are read again on every page change, so a role change shows up in the menu at
 * once. The menu only hides what a role cannot use: the server refuses the rest.
 */
export function CompanySession({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let current = true;
    // A signed-out person is sent to the login page by the shared request code.
    void getJson<Me>("/api/auth/company/me/").then((result) => {
      if (!current) return;
      if (result.ok) {
        setMe(result.data);
        setError(null);
      } else setError(result.error);
    });
    return () => {
      current = false;
    };
  }, [pathname]);

  if (!me) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  return (
    <CompanyFrame companyName={me.company_name} userName={me.name} role={me.role}>
      {children}
    </CompanyFrame>
  );
}
