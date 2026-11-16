import { ConfirmEmailChange } from "@/components/website/ConfirmEmailChange";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function ConfirmEmailChangePage({ searchParams }: Props) {
  const { token } = await searchParams;
  return <ConfirmEmailChange token={(Array.isArray(token) ? token[0] : token) ?? null} />;
}
