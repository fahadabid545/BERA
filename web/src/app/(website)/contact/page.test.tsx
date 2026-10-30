import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ContactPage from "./page";

describe("contact page", () => {
  it("shows labelled Name, Email and Message fields and a Send button", () => {
    render(<ContactPage />);
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    expect(screen.getByLabelText("Message").tagName).toBe("TEXTAREA");
    expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
  });

  it("does nothing when Send is pressed, even with empty fields", async () => {
    const { container } = render(<ContactPage />);
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.queryByText(/error/i)).toBeNull();
    expect(container.querySelector("form")).toBeTruthy();
  });
});
