import { AuthCard } from "@/components/website/AuthCard";
import { ContactForm } from "@/components/website/ContactForm";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata() {
  return pageMetadata("contact");
}

export default function ContactPage() {
  return (
    <AuthCard title="Contact" tint="sky">
      <ContactForm />
    </AuthCard>
  );
}
