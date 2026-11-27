import type { ReactNode } from "react";

import { ChatLauncher } from "./chat/ChatEntryPoints";
import { ChatProvider } from "./chat/ChatProvider";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

/** The shared frame of every public page: header, an empty content area, footer, and the public chat when it is on. */
export function SiteFrame({ children }: { children: ReactNode }) {
  return (
    <ChatProvider>
      <div className="site-skin">
        <div className="site-frame">
          <SiteHeader />
          <main className="site-main">
            <div className="site-container">{children}</div>
          </main>
          <SiteFooter />
        </div>
        <ChatLauncher />
      </div>
    </ChatProvider>
  );
}
