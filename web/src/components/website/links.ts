export const NAV_LINKS = [
  { label: "Features", href: "/features", icon: "features" },
  { label: "How it works", href: "/how-it-works", icon: "how-it-works" },
  { label: "Pricing", href: "/pricing", icon: "pricing" },
  { label: "FAQ", href: "/faq", icon: "faq" },
  { label: "Contact", href: "/contact", icon: "contact" },
] as const;

export const ACCOUNT_LINKS = {
  logIn: { label: "Log in", href: "/login" },
  signUp: { label: "Sign up", href: "/signup" },
} as const;

export const FOOTER_LINKS = [
  { label: "Terms", href: "/terms" },
  { label: "Privacy", href: "/privacy" },
  { label: "Contact", href: "/contact" },
] as const;
