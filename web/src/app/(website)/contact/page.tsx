import { ContactForm } from "@/components/website/ContactForm";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("contact");
}

export default function ContactPage() {
  return <ContactForm />;
}
