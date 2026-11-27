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
  forgotPassword: { label: "Forgot password", href: "/forgot-password" },
  resendVerification: { label: "Resend verification email", href: "/verify-email" },
} as const;

export const FOOTER_LINKS = [
  { label: "Terms", href: "/terms" },
  { label: "Privacy", href: "/privacy" },
  { label: "Contact", href: "/contact" },
] as const;

/** The footer columns. The header's links are reused so the two never drift apart. */
const link = (label: string) => NAV_LINKS.find((entry) => entry.label === label)!;
export const FOOTER_GROUPS = [
  { title: "Product", links: [link("Features"), link("How it works"), link("Pricing")] },
  { title: "Company", links: [link("FAQ"), link("Contact"), ACCOUNT_LINKS.logIn] },
  { title: "Legal", links: FOOTER_LINKS.filter((entry) => entry.label !== "Contact") },
] as const;
