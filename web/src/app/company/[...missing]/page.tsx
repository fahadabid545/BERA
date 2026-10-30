import { notFound } from "next/navigation";

// Company pages that are not built yet show the not-found page inside the company frame.
export default function MissingCompanyPage() {
  notFound();
}
