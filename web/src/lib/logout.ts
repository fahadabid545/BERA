import { postJson } from "@/lib/api";
import { navigateTo } from "@/lib/navigation";
import { currentKind } from "@/lib/session";

const LOGIN_PAGE = { company: "/login", admin: "/admin/login" } as const;

async function endAndLeave(route: "logout" | "logout-all") {
  const kind = currentKind();
  await postJson(`/api/auth/${kind}/${route}/`, {});
  // Whatever the answer, this browser should not look signed in any more.
  navigateTo(LOGIN_PAGE[kind]);
}

export function logOut() {
  return endAndLeave("logout");
}

export function logOutEverywhere() {
  return endAndLeave("logout-all");
}
