"use client";

import * as RadixMenu from "@radix-ui/react-dropdown-menu";
import Link from "next/link";
import type { ReactNode } from "react";

export type MenuItem = { label: string } & ({ href: string } | { onSelect: () => void });

/** A small dropdown of links and actions. `trigger` is the button that opens it; arrow keys and Escape work. */
export function Menu({ trigger, items }: { trigger: ReactNode; items: MenuItem[] }) {
  return (
    <RadixMenu.Root>
      <RadixMenu.Trigger asChild>{trigger}</RadixMenu.Trigger>
      <RadixMenu.Portal>
        <RadixMenu.Content className="ui-menu" align="end" sideOffset={8}>
          {items.map((item) =>
            "href" in item ? (
              <RadixMenu.Item key={item.label} asChild>
                <Link href={item.href} className="ui-menu__item">
                  {item.label}
                </Link>
              </RadixMenu.Item>
            ) : (
              <RadixMenu.Item
                key={item.label}
                className="ui-menu__item ui-menu__item--action"
                onSelect={item.onSelect}
              >
                {item.label}
              </RadixMenu.Item>
            ),
          )}
        </RadixMenu.Content>
      </RadixMenu.Portal>
    </RadixMenu.Root>
  );
}
