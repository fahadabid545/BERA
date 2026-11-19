import { UndoCompanyDeletion } from "@/components/website/UndoCompanyDeletion";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function UndoCompanyDeletionPage({ searchParams }: Props) {
  const { token } = await searchParams;
  return <UndoCompanyDeletion token={(Array.isArray(token) ? token[0] : token) ?? null} />;
}
