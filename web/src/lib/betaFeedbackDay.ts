const STORAGE_KEY = "bera-beta-feedback-day";

const today = () => new Date().toISOString().slice(0, 10);

/** Whether the beta feedback form was already offered today in this browser. Storage that is
 * blocked counts as "not yet", so the form is never missed for it. */
export function askedToday(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === today();
  } catch {
    return false;
  }
}

export function markAskedToday() {
  try {
    window.localStorage.setItem(STORAGE_KEY, today());
  } catch {
    // Without storage the form is simply offered again on the next visit.
  }
}
