import { ChangeEmailForm } from "@/components/company/ChangeEmailForm";
import { ChangePasswordForm } from "@/components/company/ChangePasswordForm";
import { ProfileForm } from "@/components/company/ProfileForm";
import { SignOutEverywhere } from "@/components/company/SignOutEverywhere";

export default function ProfilePage() {
  return (
    <>
      <ProfileForm />
      <section className="page-form" aria-labelledby="change-email">
        <h2 id="change-email">Change email</h2>
        <ChangeEmailForm />
      </section>
      <section className="page-form" aria-labelledby="change-password">
        <h2 id="change-password">Change password</h2>
        <ChangePasswordForm />
      </section>
      <div className="page-actions">
        <SignOutEverywhere />
      </div>
    </>
  );
}
