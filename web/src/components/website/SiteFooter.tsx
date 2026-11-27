import Link from "next/link";

import { FOOTER_GROUPS } from "./links";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <p className="site-footer__word" aria-hidden="true">
          Bera
        </p>
        <nav aria-label="Footer" className="site-footer__groups">
          {FOOTER_GROUPS.map((group) => (
            <div key={group.title}>
              <h2 className="site-footer__title">{group.title}</h2>
              <ul className="site-footer__list">
                {group.links.map(({ label, href }) => (
                  <li key={label}>
                    <Link href={href} className="site-footer__link">
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <p className="site-footer__base">
          <span>A product of Avennex</span>
          <span>© {new Date().getFullYear()}</span>
        </p>
      </div>
    </footer>
  );
}
