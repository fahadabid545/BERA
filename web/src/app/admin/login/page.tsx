import { Button, Input } from "@/components/ui";

export default function AdminLoginPage() {
  return (
    <form className="page-form">
      <Input label="Email" name="email" type="email" autoComplete="email" />
      <Input label="Password" name="password" type="password" autoComplete="current-password" />
      <div className="page-actions">
        <Button>Log in</Button>
      </div>
    </form>
  );
}
