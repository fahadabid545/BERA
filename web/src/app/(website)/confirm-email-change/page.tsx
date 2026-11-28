import { AuthCard } from "@/components/website/AuthCard";
import { ConfirmEmailChange } from "@/components/website/ConfirmEmailChange";
import { tokenLinkPage } from "@/lib/seo";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export const metadata = tokenLinkPage;

export default async function ConfirmEmailChangePage({ searchParams }: Props) {
  const { token } = await searchParams;
  return (
    <AuthCard title="Confirm email change" tint="sky">
      <ConfirmEmailChange token={(Array.isArray(token) ? token[0] : token) ?? null} />
    </AuthCard>
  );
}
