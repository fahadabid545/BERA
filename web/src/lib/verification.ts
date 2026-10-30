import { postJson } from "@/lib/api";

/** Asks for a new verification link; the answer is the same whatever the email is. */
export function requestNewVerificationLink(email: string) {
  return postJson<{ message: string }>("/api/auth/company/verify-email/resend/", { email });
}
