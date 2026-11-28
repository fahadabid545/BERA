import { AuthCard } from "@/components/website/AuthCard";
import { UndoCompanyDeletion } from "@/components/website/UndoCompanyDeletion";
import { tokenLinkPage } from "@/lib/seo";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export const metadata = tokenLinkPage;

export default async function UndoCompanyDeletionPage({ searchParams }: Props) {
  const { token } = await searchParams;
  return (
    <AuthCard title="Undo deletion" tint="pink">
      <UndoCompanyDeletion token={(Array.isArray(token) ? token[0] : token) ?? null} />
    </AuthCard>
  );
}
