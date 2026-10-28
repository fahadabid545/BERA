import { SiteFrame } from "@/components/website/SiteFrame";

// Pages the ticket list names but that are not built yet land here.
export default function NotFound() {
  return (
    <SiteFrame>
      <h1>Page not found</h1>
      <p>This page does not exist (yet).</p>
    </SiteFrame>
  );
}
