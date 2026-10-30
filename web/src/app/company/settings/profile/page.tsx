import { Button, Input } from "@/components/ui";

export default function ProfilePage() {
  return (
    <form className="page-form">
      <Input label="Name" autoComplete="name" />
      <Input label="Email" type="email" autoComplete="email" />
      <section className="page-form" aria-labelledby="change-password">
        <h2 id="change-password">Change password</h2>
        <Input label="Current password" type="password" autoComplete="current-password" />
        <Input label="New password" type="password" autoComplete="new-password" />
        <Input label="Confirm new password" type="password" autoComplete="new-password" />
      </section>
      <div className="page-actions">
        <Button>Save</Button>
      </div>
    </form>
  );
}
