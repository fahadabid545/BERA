import type { CompanyRole } from "@/components/company/navigation";

// Fixed fake values until the sign-in tickets provide the real signed-in user.
export const PLACEHOLDER_SESSION: { companyName: string; userName: string; role: CompanyRole } = {
  companyName: "Fake Test Company",
  userName: "Fake Owner",
  role: "owner",
};
