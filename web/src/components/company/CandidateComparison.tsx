"use client";

import { useSearchParams } from "next/navigation";

import { FILTER_KEYS } from "./CandidateFilters";
import { Matrix } from "./comparison/Matrix";
import { SideBySide } from "./comparison/SideBySide";

/** Candidates compared: with `ids` in the address, those candidates side by side; without, the
 * matrix of every candidate that passes the list's filters against every requirement. */
export function CandidateComparison({ projectId }: { projectId: string }) {
  const searchParams = useSearchParams();
  const ids = searchParams.get("ids");
  const filters = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = searchParams.get(key);
    if (value) filters.set(key, value);
  }
  return ids ? (
    <SideBySide projectId={projectId} ids={ids} />
  ) : (
    <Matrix projectId={projectId} filterQuery={filters.toString()} />
  );
}
