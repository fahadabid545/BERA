import { Button, Input } from "@/components/ui";

export default function ResetPasswordPage() {
  return (
    <form className="page-form">
      <Input label="New password" name="password" type="password" autoComplete="new-password" />
      <Input
        label="Confirm password"
        name="confirm-password"
        type="password"
        autoComplete="new-password"
      />
      <div className="page-actions">
        <Button>Save password</Button>
      </div>
    </form>
  );
}
