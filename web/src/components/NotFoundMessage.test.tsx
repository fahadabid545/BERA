import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NotFoundMessage } from "./NotFoundMessage";

describe("NotFoundMessage", () => {
  it("shows the short message and a Go home button to the given address", () => {
    render(<NotFoundMessage homeHref="/somewhere" />);
    expect(screen.getByRole("heading", { name: "This page could not be found" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go home" }).getAttribute("href")).toBe("/somewhere");
  });
});
