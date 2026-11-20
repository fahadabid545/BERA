import { AiControls } from "@/components/admin/AiControls";
import { AiSpendAlerts } from "@/components/admin/AiSpendAlerts";

export default function AiControlsPage() {
  return (
    <div className="page-stack">
      <AiControls />
      <AiSpendAlerts />
    </div>
  );
}
