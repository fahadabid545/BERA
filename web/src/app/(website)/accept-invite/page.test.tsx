import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import AcceptInvitePage from "./page";

describe("accept invite page", () => {
  it("shows labelled Your name, Password and Confirm password fields and the Join team button", () => {
    render(<AcceptInvitePage />);
    expect(screen.getByLabelText("Your name")).toBeTruthy();
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect((screen.getByLabelText("Confirm password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Join team" })).toBeTruthy();
  });

  it("does nothing when Join team is pressed", async () => {
    render(<AcceptInvitePage />);
    await userEvent.click(screen.getByRole("button", { name: "Join team" }));
    expect(screen.getByRole("button", { name: "Join team" })).toBeTruthy();
  });
});
