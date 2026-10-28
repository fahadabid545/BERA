import Link from "next/link";

import { FOOTER_LINKS } from "./links";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <nav aria-label="Footer">
          <ul className="site-footer__links">
            {FOOTER_LINKS.map(({ label, href }) => (
              <li key={label}>
                <Link href={href} className="site-footer__link">
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <p>A product of Avennex · © {new Date().getFullYear()}</p>
      </div>
    </footer>
  );
}
