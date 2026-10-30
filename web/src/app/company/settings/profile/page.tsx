import { ChangePasswordForm } from "@/components/company/ChangePasswordForm";
import { SignOutEverywhere } from "@/components/company/SignOutEverywhere";
import { Button, Input } from "@/components/ui";

export default function ProfilePage() {
  return (
    <>
      <form className="page-form">
        <Input label="Name" autoComplete="name" />
        <Input label="Email" type="email" autoComplete="email" />
        <div className="page-actions">
          <Button>Save</Button>
          <SignOutEverywhere />
        </div>
      </form>
      <section className="page-form" aria-labelledby="change-password">
        <h2 id="change-password">Change password</h2>
        <ChangePasswordForm />
      </section>
    </>
  );
}
