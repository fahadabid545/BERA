import { SignOutEverywhere } from "@/components/company/SignOutEverywhere";
import { TwoStepSettings } from "@/components/company/TwoStepSettings";

export default function SecurityPage() {
  return (
    <div className="page-stack">
      <TwoStepSettings />
      <div className="page-actions">
        <SignOutEverywhere />
      </div>
    </div>
  );
}
