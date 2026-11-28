import { AuthCard } from "@/components/website/AuthCard";
import { SignUpForm } from "@/components/website/SignUpForm";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("signup");
}

export default function SignUpPage() {
  return (
    <AuthCard title="Sign up" tint="lilac">
      <SignUpForm />
    </AuthCard>
  );
}
