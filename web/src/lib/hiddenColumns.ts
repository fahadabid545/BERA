/** Which matrix columns a person hid, kept per project in this browser only. Storage can be
 * blocked (private windows, cleared data); then every column simply shows and nothing is saved. */
const keyFor = (projectId: string) => `matrix-hidden-columns:${projectId}`;

export function readHiddenColumns(projectId: string): string[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(keyFor(projectId)) ?? "[]");
    return Array.isArray(stored) ? stored.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function writeHiddenColumns(projectId: string, hidden: string[]): void {
  try {
    window.localStorage.setItem(keyFor(projectId), JSON.stringify(hidden));
  } catch {
    // Not saved this time; the choice still holds until the page is left.
  }
}
