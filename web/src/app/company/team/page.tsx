import { TeamInvites } from "@/components/company/TeamInvites";
import { TeamMembers } from "@/components/company/TeamMembers";

export default function TeamPage() {
  return (
    <div className="page-stack">
      <TeamMembers />
      <TeamInvites />
    </div>
  );
}
