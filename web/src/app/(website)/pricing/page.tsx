import { PricingPlans } from "@/components/website/PricingPlans";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("pricing");
}

export default function PricingPage() {
  return <PricingPlans />;
}
