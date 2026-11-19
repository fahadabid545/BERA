/** Plain words for the company and subscription facts the admin screens show. */

export const STATUS_NAMES: Record<string, string> = {
  active: "Active",
  suspended: "Suspended",
  pending_deletion: "Pending deletion",
};

export const STATE_NAMES: Record<string, string> = {
  no_plan: "No plan",
  active: "Active",
  past_due: "Past due",
  cancelled: "Cancelled",
  expired: "Expired",
  granted_free: "Free plan granted",
};

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
