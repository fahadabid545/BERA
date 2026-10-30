import { ResendVerificationForm } from "@/components/website/ResendVerificationForm";
import { VerifyEmail } from "@/components/website/VerifyEmail";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

/** With a link's token: verify. Without one (from the login page): ask for a new link. */
export default async function VerifyEmailPage({ searchParams }: Props) {
  const { token } = await searchParams;
  const value = Array.isArray(token) ? token[0] : token;
  return value ? <VerifyEmail token={value} /> : <ResendVerificationForm />;
}
