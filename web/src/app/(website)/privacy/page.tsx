import { LegalPage } from "@/components/website/LegalPage";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("privacy");
}

export default function PrivacyPage() {
  return <LegalPage document="privacy" />;
}
