import "@fontsource-variable/bricolage-grotesque";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { ThemeSync } from "@/components/ThemeSync";
import { themeInitScript } from "@/lib/theme";

import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/components.css";

export const metadata = { title: "BERA" };

export default async function RootLayout({ children }: { children: ReactNode }) {
  // The middleware gives every page its own one-time code; only scripts carrying it may run.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <ThemeSync />
        {children}
      </body>
    </html>
  );
}
