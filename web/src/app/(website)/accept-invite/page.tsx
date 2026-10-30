import { Button, Input } from "@/components/ui";

export default function AcceptInvitePage() {
  return (
    <form className="page-form">
      <Input label="Your name" name="name" autoComplete="name" />
      <Input label="Password" name="password" type="password" autoComplete="new-password" />
      <Input
        label="Confirm password"
        name="confirm-password"
        type="password"
        autoComplete="new-password"
      />
      <div className="page-actions">
        <Button>Join team</Button>
      </div>
    </form>
  );
}
