import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AdminHome from "./admin/page";
import CompanyHome from "./company/page";
import WebsiteHome from "./(website)/page";

describe("the three separate areas", () => {
  it.each([
    ["company panel", CompanyHome, "BERA company panel"],
    ["admin panel", AdminHome, "BERA admin panel"],
  ])("the %s shows its own heading", (_name, Page, heading) => {
    render(<Page />);
    expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
  });
});
