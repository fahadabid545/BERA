"use client";

import * as RadixMenu from "@radix-ui/react-dropdown-menu";
import Link from "next/link";
import type { ReactNode } from "react";

export type MenuItem = { label: string; href: string };

/** A small dropdown of links. `trigger` is the button that opens it; arrow keys and Escape work. */
export function Menu({ trigger, items }: { trigger: ReactNode; items: MenuItem[] }) {
  return (
    <RadixMenu.Root>
      <RadixMenu.Trigger asChild>{trigger}</RadixMenu.Trigger>
      <RadixMenu.Portal>
        <RadixMenu.Content className="ui-menu" align="end" sideOffset={8}>
          {items.map(({ label, href }) => (
            <RadixMenu.Item key={label} asChild>
              <Link href={href} className="ui-menu__item">
                {label}
              </Link>
            </RadixMenu.Item>
          ))}
        </RadixMenu.Content>
      </RadixMenu.Portal>
    </RadixMenu.Root>
  );
}
