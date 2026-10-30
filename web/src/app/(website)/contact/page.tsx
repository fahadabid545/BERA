import { Button, Input, Textarea } from "@/components/ui";

export default function ContactPage() {
  return (
    <form className="page-form">
      <Input label="Name" name="name" autoComplete="name" />
      <Input label="Email" name="email" type="email" autoComplete="email" />
      <Textarea label="Message" name="message" />
      <div className="page-actions">
        <Button>Send</Button>
      </div>
    </form>
  );
}
