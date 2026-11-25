import { LegalPage } from "@/components/website/LegalPage";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("terms");
}

export default function TermsPage() {
  return <LegalPage document="terms" />;
}
