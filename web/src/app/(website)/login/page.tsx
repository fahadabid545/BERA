import { Button, Input, TextLink } from "@/components/ui";
import { ACCOUNT_LINKS } from "@/components/website/links";

export default function LoginPage() {
  return (
    <form className="page-form">
      <Input label="Email" name="email" type="email" autoComplete="email" />
      <Input label="Password" name="password" type="password" autoComplete="current-password" />
      <div className="page-actions">
        <Button>Log in</Button>
      </div>
      <div className="page-links">
        <TextLink href={ACCOUNT_LINKS.forgotPassword.href}>Forgot password?</TextLink>
        <TextLink href={ACCOUNT_LINKS.resendVerification.href}>
          {ACCOUNT_LINKS.resendVerification.label}
        </TextLink>
        <TextLink href={ACCOUNT_LINKS.signUp.href}>Create an account</TextLink>
      </div>
    </form>
  );
}
