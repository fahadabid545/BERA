import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { THEME_STORAGE_KEY } from "@/lib/theme";

import {
  Button,
  Card,
  Checkbox,
  Dialog,
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

  it("show an error with an icon and the word, not colour alone", () => {
    render(<Input label="Email" error="Enter a valid email address." />);
    const message = document.querySelector(".ui-error")!;
    expect(message.querySelector("svg")).not.toBeNull();
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

describe("Tag", () => {
  it.each(["success", "warning", "danger", "live"] as const)(
    "%s status has an icon as well as words",
    (variant) => {
      render(<Tag variant={variant}>Status words</Tag>);
      const tag = screen.getByText("Status words");
      expect(tag.querySelector("svg, .ui-tag__dot")).not.toBeNull();
    },
  );
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
