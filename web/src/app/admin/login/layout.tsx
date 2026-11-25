import type { ReactNode } from "react";
import { privatePage } from "@/lib/seo";

// The admin sign-in is separate from the website and from the panel: no header, footer or sidebar.
export const metadata = privatePage;

export default function AdminLoginLayout({ children }: { children: ReactNode }) {
  return (
    <main className="site-main">
      <div className="site-container">{children}</div>
    </main>
  );
}
