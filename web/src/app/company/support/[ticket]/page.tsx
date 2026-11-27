import { TicketView } from "@/components/company/support/TicketView";

export default async function TicketRoute({ params }: { params: Promise<{ ticket: string }> }) {
  const { ticket } = await params;
  return <TicketView id={ticket} />;
}
