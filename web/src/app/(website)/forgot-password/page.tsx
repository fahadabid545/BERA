import { Button, Input, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";

export default function ForgotPasswordPage() {
  return (
    <form className="page-form">
      <Input label="Email" name="email" type="email" autoComplete="email" />
      <div className="page-actions">
        <Button>Send reset link</Button>
      </div>
      <div className="page-links">
        <TextLink href={ACCOUNT_LINKS.logIn.href}>Back to Log in</TextLink>
      </div>
    </form>
  );
}
