import { currentAddress, navigateTo } from "@/lib/navigation";

const COMPANY_LOGIN = "/login";
const ADMIN_LOGIN = "/admin/login";

let runningUploads = 0;
let warnAboutUploads: (() => void) | null = null;

/** Which area of the product the person is in, from the address of the page. */
export function currentKind(): "company" | "admin" {
  return window.location.pathname.startsWith("/admin") ? "admin" : "company";
}

/**
 * Call when a file starts uploading and call the returned function when it ends (success or
 * failure). While any upload runs, an ended session shows a warning instead of leaving the page
 * and silently losing the files.
 */
export function startUpload(): () => void {
  runningUploads += 1;
  let finished = false;
  return () => {
    if (!finished) {
      finished = true;
      runningUploads -= 1;
    }
  };
}

/** The popup that warns about running uploads registers itself here. */
export function onUploadsAtRisk(handler: (() => void) | null) {
  warnAboutUploads = handler;
}

/** Where to sign in again, so that signing in brings the person back to this page. */
export function loginAddressForHere(): string {
  if (currentKind() === "admin") return ADMIN_LOGIN;
  return `${COMPANY_LOGIN}?next=${encodeURIComponent(currentAddress())}`;
}

export function goToLogin() {
  navigateTo(loginAddressForHere());
}

/** The server says the session is over and could not be renewed. */
export function sessionEnded() {
  if (runningUploads > 0 && warnAboutUploads) warnAboutUploads();
  else goToLogin();
}
