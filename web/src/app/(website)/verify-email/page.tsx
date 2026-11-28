import { AuthCard } from "@/components/website/AuthCard";
import { ResendVerificationForm } from "@/components/website/ResendVerificationForm";
import { VerifyEmail } from "@/components/website/VerifyEmail";
import { tokenLinkPage } from "@/lib/seo";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

/** With a link's token: verify. Without one (from the login page): ask for a new link. */
export const metadata = tokenLinkPage;

export default async function VerifyEmailPage({ searchParams }: Props) {
  const { token } = await searchParams;
  const value = Array.isArray(token) ? token[0] : token;
  return (
    <AuthCard title="Verify email" tint="lime">
      {value ? <VerifyEmail token={value} /> : <ResendVerificationForm />}
    </AuthCard>
  );
}
