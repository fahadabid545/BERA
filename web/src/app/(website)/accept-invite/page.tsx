import { Button, Input } from "@/components/ui";
import { NewPasswordFields } from "@/components/website/NewPasswordFields";

export default function AcceptInvitePage() {
  return (
    <form className="page-form">
      <Input label="Your name" name="name" autoComplete="name" />
      <NewPasswordFields
        passwordLabel="Password"
        passwordName="password"
        confirm={{ label: "Confirm password", name: "confirm-password" }}
      />
      <div className="page-actions">
        <Button>Join team</Button>
      </div>
    </form>
  );
}
