// @vitest-environment node
import { readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { blockedAdminHrefs, type AdminRole } from "@/components/admin/navigation";
import { blockedCompanyHrefs, type CompanyRole } from "@/components/company/navigation";
import { isCurrentPath } from "@/components/panel/navigation";

const APP = path.join(process.cwd(), "src", "app");

/** Every page address under a folder, with groups like (panel) left out of the address. */
function pageRoutes(directory: string, parents: string[] = []): string[] {
  const found: string[] = [];
  for (const name of readdirSync(directory)) {
    const full = path.join(directory, name);
    if (statSync(full).isDirectory()) {
      const segment = /^\(.*\)$/.test(name) ? [] : [name];
      found.push(...pageRoutes(full, [...parents, ...segment]));
    } else if (name === "page.tsx") {
      found.push("/" + parents.join("/"));
    }
  }
  return found;
}

// Written out by hand on purpose: a page added later fails here until someone decides who may
// open it, instead of quietly being open to everybody.
const COMPANY_PAGES: Record<string, readonly CompanyRole[]> = {
  "/company": ["owner", "member"],
  "/company/dashboard/print": ["owner", "member"],
  "/company/projects": ["owner", "member"],
  "/company/projects/new": ["owner", "member"],
  "/company/projects/[project]": ["owner", "member"],
  "/company/projects/[project]/requirements": ["owner", "member"],
  "/company/projects/[project]/candidates": ["owner", "member"],
  "/company/projects/[project]/settings": ["owner", "member"],
  "/company/projects/[project]/compare": ["owner", "member"],
  "/company/projects/[project]/candidates/[candidate]": ["owner", "member"],
  "/company/downloads/[id]": ["owner", "member"],
  "/company/settings/profile": ["owner", "member"],
  "/company/settings/company": ["owner"],
  "/company/team": ["owner"],
  "/company/billing": ["owner"],
  "/company/billing/return": ["owner"],
  "/company/advanced/defaults": ["owner"],
  "/company/advanced/retention": ["owner"],
  "/company/advanced/security": ["owner"],
  "/company/advanced/notifications": ["owner"],
  "/company/advanced/data": ["owner"],
  "/company/advanced/api-keys": ["owner"],
};

const ADMIN_PAGES: Record<string, readonly AdminRole[]> = {
  "/admin": ["super", "support"],
  "/admin/dashboard/print": ["super", "support"],
  "/admin/companies": ["super", "support"],
  "/admin/companies/[company]": ["super", "support"],
  "/admin/operations/jobs": ["super", "support"],
  "/admin/operations/announcements": ["super", "support"],
  "/admin/operations/data-requests": ["super", "support"],
  "/admin/operations/feedback": ["super", "support"],
  "/admin/operations/payments": ["super"],
  "/admin/operations/cost-versus-revenue": ["super"],
  "/admin/plans": ["super"],
  "/admin/plans/[plan]": ["super"],
  "/admin/ai/playground": ["super"],
  "/admin/ai/models": ["super"],
  "/admin/ai/prompts": ["super"],
  "/admin/settings/general": ["super"],
  "/admin/settings/audit-log": ["super"],
  "/admin/settings/admins": ["super"],
  "/admin/advanced/platform-values": ["super"],
  "/admin/advanced/limits": ["super"],
  "/admin/advanced/rate-limits": ["super"],
  "/admin/advanced/security": ["super"],
  "/admin/advanced/ai-controls": ["super"],
  "/admin/advanced/maintenance": ["super"],
};

// Pages with their own checks outside the panel (sign-in, invitations) or only a "not found".
const NOT_IN_THE_PANEL = ["/admin/login", "/admin/accept-invite"];
const CATCH_ALLS = ["/company/[...missing]", "/admin/[...missing]"];

const concrete = (route: string) => route.replace(/\[[^\]]+\]/g, "example");
const refused = (blocked: string[], route: string) =>
  blocked.some((href) => isCurrentPath(concrete(route), href));

describe("who may open each company page", () => {
  const found = pageRoutes(path.join(APP, "company"), ["company"]);
  const pages = found.filter((route) => !CATCH_ALLS.includes(route));

  it("has a decision for every page, and no decision for a page that is gone", () => {
    expect(pages.sort()).toEqual(Object.keys(COMPANY_PAGES).sort());
  });

  it.each(Object.entries(COMPANY_PAGES))("%s", (route, allowed) => {
    for (const role of ["owner", "member"] as const) {
      expect(refused(blockedCompanyHrefs(role), route), `${role} on ${route}`).toBe(
        !allowed.includes(role),
      );
    }
  });
});

describe("who may open each admin page", () => {
  const found = pageRoutes(path.join(APP, "admin"), ["admin"]);
  const pages = found.filter(
    (route) => !CATCH_ALLS.includes(route) && !NOT_IN_THE_PANEL.includes(route),
  );

  it("has a decision for every page, and no decision for a page that is gone", () => {
    expect(pages.sort()).toEqual(Object.keys(ADMIN_PAGES).sort());
  });

  it.each(Object.entries(ADMIN_PAGES))("%s", (route, allowed) => {
    for (const role of ["super", "support"] as const) {
      expect(refused(blockedAdminHrefs(role), route), `${role} on ${route}`).toBe(
        !allowed.includes(role),
      );
    }
  });
});
