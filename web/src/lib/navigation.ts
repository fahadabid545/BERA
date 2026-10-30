/** Leaves the current page for another address. Kept in one place so tests can watch it. */
export function navigateTo(address: string) {
  window.location.assign(address);
}

export function currentAddress(): string {
  return window.location.pathname + window.location.search;
}
