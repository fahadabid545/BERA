import { NotFoundMessage } from "@/components/NotFoundMessage";
import { SiteFrame } from "@/components/website/SiteFrame";

export default function NotFound() {
  return (
    <SiteFrame>
      <NotFoundMessage homeHref="/" />
    </SiteFrame>
  );
}
