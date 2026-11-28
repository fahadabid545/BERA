import { AuthCard } from "@/components/website/AuthCard";
import { ForgotPasswordForm } from "@/components/website/ForgotPasswordForm";
import { privatePage } from "@/lib/seo";

export const metadata = privatePage;

export default function ForgotPasswordPage() {
  return (
    <AuthCard title="Forgot password" tint="peach">
      <ForgotPasswordForm />
    </AuthCard>
  );
}
