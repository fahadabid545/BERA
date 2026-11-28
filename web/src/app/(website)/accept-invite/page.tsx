import { AuthCard } from "@/components/website/AuthCard";
import { AcceptInviteForm } from "@/components/website/AcceptInviteForm";
import { tokenLinkPage } from "@/lib/seo";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export const metadata = tokenLinkPage;

export default async function AcceptInvitePage({ searchParams }: Props) {
  const { token } = await searchParams;
  const value = Array.isArray(token) ? token[0] : token;
  return (
    <AuthCard title="Accept invite" tint="lilac">
      <AcceptInviteForm token={value ?? null} />
    </AuthCard>
  );
}
