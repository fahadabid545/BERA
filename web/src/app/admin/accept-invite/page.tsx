import { AdminAcceptInviteForm } from "@/components/admin/AdminAcceptInviteForm";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function AdminAcceptInvitePage({ searchParams }: Props) {
  const { token } = await searchParams;
  const value = Array.isArray(token) ? token[0] : token;
  return <AdminAcceptInviteForm token={value ?? null} />;
}
