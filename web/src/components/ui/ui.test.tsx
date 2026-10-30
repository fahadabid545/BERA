import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { THEME_STORAGE_KEY } from "@/lib/theme";

import {
  Button,
  Card,
  Checkbox,
  Textarea,
  TextLink,
  Dialog,
  Menu,
  Input,
  Select,
  Table,
  Tabs,
  Tag,
  ThemeToggle,
  Tooltip,
} from ".";

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("Button", () => {
  it.each(["primary", "secondary", "danger"] as const)("has a %s look", (variant) => {
    render(<Button variant={variant}>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" }).className).toContain(`ui-button--${variant}`);
  });

  it("does not submit a form unless asked to", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button").getAttribute("type")).toBe("button");
  });
});

describe("form fields", () => {
  it("connect label, hint and error to the input", () => {
    render(<Input label="Email" hint="Work address" error="Enter a valid email address." />);
    const input = screen.getByLabelText("Email");

    expect(input.getAttribute("aria-invalid")).toBe("true");
    const described = input.getAttribute("aria-describedby")!.split(" ");
    expect(described).toHaveLength(2);
    expect(document.getElementById(described[0])?.textContent).toBe("Work address");
    expect(document.getElementById(described[1])?.textContent).toContain(
      "Enter a valid email address.",
    );
  });

  it("show an error in plain words with no icon, announced as an error", () => {
    render(<Input label="Email" error="Enter a valid email address." />);
    const message = document.querySelector(".ui-error")!;
    expect(message.querySelector("svg")).toBeNull();
    expect(message.textContent).toContain("Error: Enter a valid email address.");
  });

  it("are not marked invalid without an error", () => {
    render(<Input label="Name" />);
    const input = screen.getByLabelText("Name");
    expect(input.hasAttribute("aria-invalid")).toBe(false);
    expect(input.hasAttribute("aria-describedby")).toBe(false);
  });

  it("let a select be chosen by its label", async () => {
    render(
      <Select
        label="Keep CVs for"
        options={[
          { value: "30", label: "30 days" },
          { value: "180", label: "180 days" },
        ]}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Keep CVs for"), "180");
    expect((screen.getByLabelText("Keep CVs for") as HTMLSelectElement).value).toBe("180");
  });

  it("let a checkbox be toggled with the keyboard", async () => {
    render(<Checkbox label="Notify me" />);
    await userEvent.tab();
    await userEvent.keyboard(" ");
    expect((screen.getByLabelText("Notify me") as HTMLInputElement).checked).toBe(true);
  });
});

describe("TextLink", () => {
  it("is a link to its address with the underlined link style", () => {
    render(<TextLink href="/login">Log in</TextLink>);
    const link = screen.getByRole("link", { name: "Log in" });
    expect(link.getAttribute("href")).toBe("/login");
    expect(link.className).toContain("ui-text-link");
  });
});

describe("Textarea", () => {
  it("is labelled and shows its error in words", () => {
    render(<Textarea label="Message" error="Write a message." />);
    const box = screen.getByLabelText("Message");
    expect(box.tagName).toBe("TEXTAREA");
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Write a message.")).toBeTruthy();
  });
});

describe("Checkbox with links", () => {
  it("can hold links in its label without the links toggling it", async () => {
    render(<Checkbox label={<TextLink href="/terms">Terms</TextLink>} />);
    expect(screen.getByRole("link", { name: "Terms" }).getAttribute("href")).toBe("/terms");
    expect(screen.getByRole("checkbox", { name: "Terms" })).toBeTruthy();
  });
});

describe("Tag", () => {
  it.each(["neutral", "success", "warning", "danger", "live", "admin"] as const)(
    "%s status is shown in words with its own surface class and no icon",
    (variant) => {
      render(<Tag variant={variant}>Status words</Tag>);
      const tag = screen.getByText("Status words");
      expect(tag.classList.contains(`ui-tag--${variant}`)).toBe(true);
      expect(tag.querySelector("svg")).toBeNull();
    },
  );

  it("shows a pulsing dot only for live", () => {
    render(<Tag variant="live">Live</Tag>);
    expect(document.querySelector(".ui-tag__dot")).not.toBeNull();
  });
});

describe("Card and Table", () => {
  it("marks a selected card", () => {
    render(<Card selected>Chosen</Card>);
    expect(screen.getByText("Chosen").getAttribute("data-selected")).toBe("true");
  });

  it("gives the scrolling table area a name and keyboard access", () => {
    render(
      <Table label="Candidates">
        <tbody>
          <tr>
            <td>Row</td>
          </tr>
        </tbody>
      </Table>,
    );
    const region = screen.getByRole("region", { name: "Candidates" });
    expect(region.getAttribute("tabindex")).toBe("0");
    expect(within(region).getByRole("table")).toBeTruthy();
  });
});

describe("Tabs", () => {
  it("switch with the arrow keys", async () => {
    render(
      <Tabs
        label="Sections"
        tabs={[
          { value: "a", label: "First", content: <p>First content</p> },
          { value: "b", label: "Second", content: <p>Second content</p> },
        ]}
      />,
    );
    expect(screen.getByText("First content")).toBeTruthy();

    await userEvent.tab();
    await userEvent.keyboard("{ArrowRight}");

    expect(screen.getByRole("tab", { name: "Second" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Second content")).toBeTruthy();
  });
});

describe("Dialog", () => {
  it("opens with a title and description, and Escape closes it", async () => {
    render(
      <Dialog
        trigger={<Button>Open</Button>}
        title="Delete project?"
        description="This cannot be undone."
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    const dialog = screen.getByRole("dialog", { name: "Delete project?" });
    expect(within(dialog).getByText("This cannot be undone.")).toBeTruthy();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("as a confirmation, runs the action only after the confirm button", async () => {
    const onConfirm = vi.fn();
    render(
      <Dialog
        trigger={<Button>Open</Button>}
        title="Delete project?"
        confirmLabel="Delete"
        destructive
        onConfirm={onConfirm}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does nothing when cancelled", async () => {
    const onConfirm = vi.fn();
    render(
      <Dialog
        trigger={<Button>Open</Button>}
        title="Delete project?"
        confirmLabel="Delete"
        onConfirm={onConfirm}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("Menu", () => {
  it("opens a list of links from its trigger and closes with Escape", async () => {
    render(
      <Menu
        trigger={<Button>Account</Button>}
        items={[
          { label: "Profile", href: "/profile" },
          { label: "Log out", href: "/login" },
        ]}
      />,
    );
    expect(screen.queryByRole("menuitem")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Account" }));
    expect(screen.getByRole("menuitem", { name: "Profile" }).getAttribute("href")).toBe("/profile");
    expect(screen.getByRole("menuitem", { name: "Log out" }).getAttribute("href")).toBe("/login");

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menuitem")).toBeNull();
  });
});

describe("Tooltip", () => {
  it("appears when the element gets keyboard focus", async () => {
    render(
      <Tooltip content="More help">
        <Button>Help</Button>
      </Tooltip>,
    );
    await userEvent.tab();
    expect((await screen.findAllByText("More help")).length).toBeGreaterThan(0);
  });
});

describe("ThemeToggle", () => {
  it("starts light, switches to dark and remembers the choice", async () => {
    render(<ThemeToggle />);
    const toggle = screen.getByRole("switch", { name: "Dark mode" });
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    await userEvent.click(toggle);

    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("shows dark when dark was remembered", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeToggle />);
    expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true");
  });
});
