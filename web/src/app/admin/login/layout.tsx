import type { ReactNode } from "react";

// The admin sign-in is separate from the website and from the panel: no header, footer or sidebar.
export default function AdminLoginLayout({ children }: { children: ReactNode }) {
  return (
    <main className="site-main">
      <div className="site-container">{children}</div>
    </main>
  );
}
