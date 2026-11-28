import { SiteNotFound } from "@/components/website/SiteNotFound";
import { SiteFrame } from "@/components/website/SiteFrame";

export default function NotFound() {
  return (
    <SiteFrame>
      <SiteNotFound homeHref="/" />
    </SiteFrame>
  );
}
