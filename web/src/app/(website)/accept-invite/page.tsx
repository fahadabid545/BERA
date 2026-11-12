import { AcceptInviteForm } from "@/components/website/AcceptInviteForm";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function AcceptInvitePage({ searchParams }: Props) {
  const { token } = await searchParams;
  const value = Array.isArray(token) ? token[0] : token;
  return <AcceptInviteForm token={value ?? null} />;
}
