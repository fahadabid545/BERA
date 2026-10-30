import { notFound } from "next/navigation";

// Admin pages that are not built yet show the not-found page inside the admin frame.
export default function MissingAdminPage() {
  notFound();
}
