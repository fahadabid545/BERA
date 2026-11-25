import { ForgotPasswordForm } from "@/components/website/ForgotPasswordForm";
import { privatePage } from "@/lib/seo";

export const metadata = privatePage;

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
