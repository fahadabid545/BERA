import { LoginForm } from "@/components/website/LoginForm";
import { pageMetadata } from "@/lib/seo";

type Props = { searchParams: Promise<{ next?: string | string[] }> };

export async function generateMetadata() {
  return pageMetadata("login");
}

export default async function LoginPage({ searchParams }: Props) {
  const { next } = await searchParams;
  return <LoginForm next={next} />;
}
