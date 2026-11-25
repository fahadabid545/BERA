import { ResetPasswordForm } from "@/components/website/ResetPasswordForm";
import { tokenLinkPage } from "@/lib/seo";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export const metadata = tokenLinkPage;

export default async function ResetPasswordPage({ searchParams }: Props) {
  const { token } = await searchParams;
  const value = Array.isArray(token) ? token[0] : token;
  return <ResetPasswordForm token={value ?? null} />;
}
