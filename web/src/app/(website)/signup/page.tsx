import { Button, Checkbox, Input, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS, FOOTER_LINKS } from "@/components/website/links";

const TERMS_LINK = FOOTER_LINKS.find((link) => link.label === "Terms")!;
const PRIVACY_LINK = FOOTER_LINKS.find((link) => link.label === "Privacy")!;

export default function SignUpPage() {
  return (
    <form className="page-form">
      <Input label="Company name" name="company" autoComplete="organization" />
      <Input label="Your name" name="name" autoComplete="name" />
      <Input label="Email" name="email" type="email" autoComplete="email" />
      <Input label="Password" name="password" type="password" autoComplete="new-password" />
      <Checkbox
        name="accept"
        label={
          <>
            I accept the <TextLink href={TERMS_LINK.href}>Terms</TextLink> and{" "}
            <TextLink href={PRIVACY_LINK.href}>Privacy Policy</TextLink>
          </>
        }
      />
      <div className="page-actions">
        <Button>Create account</Button>
      </div>
      <div className="page-links">
        <TextLink href={ACCOUNT_LINKS.logIn.href}>Already have an account? Log in</TextLink>
      </div>
    </form>
  );
}
