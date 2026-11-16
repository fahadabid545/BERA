"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * The chosen tab of a page, kept in the address (`?tab=...`) so a link or a return visit shows
 * the same tab. An unknown or missing value is the first one; other parts of the address stay.
 */
export function useTabParam<T extends string>(
  values: readonly T[],
  parameter = "tab",
): [T, (next: string) => void] {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requested = searchParams.get(parameter);
  const active = values.find((value) => value === requested) ?? values[0];
  const choose = (next: string) => {
    const query = new URLSearchParams(searchParams.toString());
    query.set(parameter, next);
    router.replace(`${pathname}?${query}`, { scroll: false });
  };
  return [active, choose];
}
