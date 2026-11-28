import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const read = (name: string) => readFileSync(join(__dirname, name), "utf8");
const tokensCss = read("tokens.css");
const baseCss = read("base.css");
const componentsCss = read("components.css");
const websiteCss = read("website.css");

function tokensOf(selectorPattern: RegExp): Record<string, string> {
  const block = tokensCss.match(selectorPattern)?.[1] ?? "";
  return Object.fromEntries(
    [...block.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]),
  );
}

const MODES = {
  light: tokensOf(/:root,\s*:root\[data-theme="light"\]\s*\{([^}]*)\}/),
  dark: tokensOf(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/),
};

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => {
    const value = parseInt(hex.slice(start, start + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(first: string, second: string): number {
  const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

// The chart colours: each is a fill with its own text colour, and a soft tint for rows and tags.
const DATA_COLOURS = ["blue", "violet", "amber", "coral", "teal"] as const;

// [foreground token, background token]: readable text needs 4.5:1.
const TEXT_PAIRS = [
  ["color-text", "color-bg"],
  ["color-text", "color-surface"],
  ["color-text", "color-surface-muted"],
  ["color-text", "color-accent-soft"],
  ["color-text-muted", "color-bg"],
  ["color-text-muted", "color-surface"],
  ["color-on-accent", "color-accent"],
  ["color-on-danger", "color-danger"],
  ["color-danger-text", "color-danger-bg"],
  ["color-danger-text", "color-surface"],
  ["color-danger-text", "color-bg"],
  ["color-warning-text", "color-warning-bg"],
  ["color-success-text", "color-success-bg"],
  ["color-tooltip-text", "color-tooltip-bg"],
  ["color-text-muted", "color-surface-muted"],
  ["color-bg", "color-text"],
  ["color-admin-text", "color-admin-bg"],
  ["color-admin-text", "color-admin-hover"],
  ["color-admin-text", "color-admin-active"],
] as const;

// The pastel card tints: ink text and muted text must stay readable on every one.
const TINTS = ["lime", "lilac", "peach", "sky", "pink"] as const;
const TINT_PAIRS = TINTS.flatMap((name): [string, string][] => [
  ["color-text", `color-tint-${name}`],
  ["color-text-muted", `color-tint-${name}`],
]);

const DATA_TEXT_PAIRS = DATA_COLOURS.flatMap((name): [string, string][] => [
  [`color-on-data-${name}`, `color-data-${name}`],
  ["color-text", `color-data-${name}-soft`],
  ["color-text-muted", `color-data-${name}-soft`],
]);

// Borders, focus rings and other parts needed to use a control: 3:1.
const CONTROL_PAIRS = [
  ["color-control-border", "color-surface"],
  ["color-control-border", "color-bg"],
  ["color-focus", "color-bg"],
  ["color-focus", "color-surface"],
  ["color-focus", "color-surface-muted"],
  ["color-danger-text", "color-surface"],
  ["color-checked-border", "color-surface"],
  ["color-checked-border", "color-bg"],
  ["color-danger", "color-surface"],
  ["color-admin-focus", "color-admin-bg"],
] as const;

describe.each(Object.entries(MODES))("%s mode colours", (_mode, tokens) => {
  it("uses the brand colours", () => {
    expect(tokens["color-accent"]).toBe("#5bd62a");
    expect(tokens["color-on-accent"]).toBe("#0d100c");
  });

  it.each([...TEXT_PAIRS, ...DATA_TEXT_PAIRS, ...TINT_PAIRS])(
    "text %s on %s is readable (4.5:1)",
    (foreground, background) => {
      expect(contrast(tokens[foreground], tokens[background])).toBeGreaterThanOrEqual(4.5);
    },
  );

  it.each(CONTROL_PAIRS)("%s against %s is clearly visible (3:1)", (foreground, background) => {
    expect(contrast(tokens[foreground], tokens[background])).toBeGreaterThanOrEqual(3);
  });
});

describe("light and dark modes", () => {
  it("define exactly the same colour tokens", () => {
    expect(Object.keys(MODES.dark).sort()).toEqual(Object.keys(MODES.light).sort());
  });

  it("have a soft off-white light background and a near-black dark background", () => {
    expect(luminance(MODES.light["color-bg"])).toBeGreaterThan(0.9);
    expect(luminance(MODES.dark["color-bg"])).toBeLessThan(0.01);
  });
});

describe("focus", () => {
  it("is shown on every element for keyboard users", () => {
    expect(baseCss).toMatch(/:focus-visible\s*\{[^}]*outline:\s*3px solid var\(--color-focus\)/);
  });

  it("is never switched off anywhere", () => {
    for (const css of [baseCss, componentsCss]) {
      expect(css).not.toMatch(/outline:\s*(none|0)\b/);
    }
  });
});

describe("colour rules", () => {
  it("never uses the green accent as a text colour", () => {
    for (const css of [baseCss, componentsCss]) {
      expect(css).not.toMatch(/(^|[;{\s])color:\s*var\(--color-accent\)/);
    }
  });

  it("uses the glow only on live or selected elements", () => {
    const rules = [...componentsCss.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
    const glowing = rules.filter(([, , body]) => body.includes("var(--glow)"));
    expect(glowing.length).toBeGreaterThan(0);
    for (const [, selector] of glowing) {
      expect(selector).toMatch(/checked|selected|live|__dot/);
    }
  });

  it("stops animations for people who ask for less motion", () => {
    expect(baseCss).toContain("prefers-reduced-motion: reduce");
  });
});

describe("fonts and touch size", () => {
  it("assigns the three font families", () => {
    expect(tokensCss).toContain('--font-heading: "Bricolage Grotesque Variable"');
    expect(tokensCss).toContain('--font-body: "IBM Plex Sans"');
    expect(tokensCss).toContain('--font-mono: "IBM Plex Mono"');
  });

  it("keeps controls at least 44px tall and inputs at 16px so phones do not zoom", () => {
    expect(tokensCss).toContain("--control-height: 2.75rem");
    expect(componentsCss).toMatch(/\.ui-input[^{]*\{[^}]*font:\s*var\(--text-md\)/);
  });
});

describe("highlight styles and icon transitions", () => {
  it("shows the filled icon only inside the current item, with a fade/scale transition", () => {
    expect(componentsCss).toMatch(/\[aria-current="page"\] \.ui-toggle-icon__filled/);
    expect(componentsCss).toMatch(/\.ui-toggle-icon svg\s*\{[^}]*transition:/);
    expect(componentsCss).toMatch(/\.ui-toggle-icon__filled\s*\{[^}]*opacity:\s*0/);
  });

  it("uses a pill for content highlights and a row tint plus bar for tables", () => {
    expect(componentsCss).toMatch(/\.ui-icon-item\s*\{[^}]*border-radius:\s*var\(--radius-pill\)/);
    expect(componentsCss).toMatch(/\.ui-table tbody tr:not\(\[data-selected="true"\]\):hover td/);
    expect(componentsCss).toMatch(
      /\.ui-table tr\[data-selected="true"\] td\s*\{[^}]*repeating-linear-gradient/,
    );
  });

  it("shares one content column between the header, page and footer", () => {
    expect(componentsCss).toMatch(
      /\.site-container\s*\{[^}]*max-width:\s*var\(--container-width\)/,
    );
    expect(componentsCss).toMatch(
      /\.site-header__inner\s*\{[^}]*max-width:\s*var\(--container-width\)/,
    );
    expect(websiteCss).toMatch(
      /\.site-footer__inner\s*\{[^}]*max-width:\s*var\(--container-width\)/,
    );
  });
});

describe("buttons, cards, rows and tags", () => {
  it("makes disabled buttons flat grey with no green", () => {
    const rule = componentsCss.match(/\.ui-button:disabled\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toContain("var(--color-surface-muted)");
    expect(rule).not.toContain("accent");
  });

  it("flips the delete button on hover", () => {
    const rule =
      componentsCss.match(/\.ui-button--danger:not\(:disabled\):hover\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toContain("background: var(--color-surface)");
    expect(rule).toContain("color: var(--color-danger-text)");
  });

  it("marks a selected card with a raised shadow, never a green outline", () => {
    const rule = componentsCss.match(/\.ui-card\[data-selected="true"\]\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toContain("var(--shadow-raised)");
    expect(rule).not.toContain("accent");
    expect(rule).not.toContain("glow");
  });

  it("selects table rows without a green bar or green tint", () => {
    const rule =
      componentsCss.match(/\.ui-table tr\[data-selected="true"\] td\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).not.toContain("accent");
    expect(componentsCss).not.toContain("inset 4px 0 0");
  });

  it("gives every tag status its own surface and no icons", () => {
    for (const variant of ["success", "warning", "danger", "live"]) {
      expect(componentsCss).toContain(`.ui-tag--${variant} {`);
    }
    expect(componentsCss).toMatch(/\.ui-tag--warning\s*\{[^}]*repeating-linear-gradient/);
  });
});

describe("popup", () => {
  it("centres its buttons and fades in, and motion stops for reduced motion", () => {
    expect(componentsCss).toMatch(/\.ui-dialog__actions\s*\{[^}]*justify-content:\s*center/);
    expect(componentsCss).toMatch(/\.ui-dialog\s*\{[^}]*animation:\s*ui-dialog-in/);
    expect(baseCss).toContain("prefers-reduced-motion: reduce");
  });

  it("hides the Next.js development badge", () => {
    expect(readFileSync(join(__dirname, "../../next.config.ts"), "utf8")).toContain(
      "devIndicators: false",
    );
  });
});

describe("company panel frame", () => {
  it("collapses to icons on tablets and slides out on phones", () => {
    expect(componentsCss).toMatch(/@media \(min-width: 40rem\) and \(max-width: 63\.99rem\)/);
    expect(componentsCss).toMatch(/--sidebar-width: var\(--sidebar-rail-width\)/);
    expect(componentsCss).toMatch(/@media \(max-width: 39\.99rem\)/);
    expect(componentsCss).toMatch(/\.panel-sidebar\s*\{[^}]*transform: translateX\(-100%\)/);
  });

  it("keeps hidden labels available to screen readers", () => {
    const tablet = componentsCss.split("@media (min-width: 40rem)")[1] ?? "";
    expect(tablet).toMatch(/\.panel-label,[^{]*\{[^}]*clip: rect\(0 0 0 0\)/);
    expect(tablet).not.toMatch(/\.panel-label[^{]*\{[^}]*display: none/);
  });
});

describe("theme choice survives page re-renders", () => {
  it("does not hard-code a theme on <html>, so React never resets the saved one", () => {
    const layout = readFileSync(join(__dirname, "../app/layout.tsx"), "utf8");
    expect(layout).not.toMatch(/<html[^>]*data-theme/);
  });
});

describe("admin look", () => {
  it("has an ink sidebar that is dark in both modes, a green stripe and an Admin badge", () => {
    for (const tokens of Object.values(MODES)) {
      expect(luminance(tokens["color-admin-bg"])).toBeLessThan(0.01);
    }
    expect(componentsCss).toMatch(
      /\.panel-frame \.panel-sidebar\s*\{[^}]*background: var\(--color-admin-bg\)/,
    );
    expect(componentsCss).toMatch(/\.panel--admin \.panel-topbar\s*\{[^}]*var\(--color-accent\)/);
    expect(componentsCss).toMatch(/\.ui-tag--admin\s*\{[^}]*background: var\(--color-text\)/);
  });

  it("keeps the focus ring visible on the ink sidebar", () => {
    expect(componentsCss).toMatch(
      /\.panel-frame \.panel-sidebar\s*\{[^}]*--color-focus: var\(--color-admin-focus\)/,
    );
  });
});

describe("Advanced divider", () => {
  it("draws a divider above separated sidebar items, in the admin colours too", () => {
    expect(componentsCss).toMatch(
      /\.panel-nav > li\[data-separated="true"\]\s*\{[^}]*border-top: 1px solid var\(--color-border\)/,
    );
    expect(componentsCss).toMatch(
      /\.panel-frame \.panel-nav > li\[data-separated="true"\]\s*\{[^}]*var\(--color-admin-hover\)/,
    );
  });
});

// The public website is light only, so its subtree re-declares the light colours.
describe("website skin", () => {
  const skin = tokensOf(/\.site-skin\s*\{([^}]*)\}/);

  it("uses the brand green", () => {
    expect(skin["color-accent"]).toBe("#5bd62a");
  });

  it("re-declares every light colour, so a dark theme can never leak into it", () => {
    for (const name of Object.keys(MODES.light)) {
      if (
        name.startsWith("color-") &&
        !name.startsWith("color-data-") &&
        !name.startsWith("color-on-data-")
      ) {
        const exempt = ["color-qr-background", "color-hatch", "color-admin-"].some((prefix) =>
          name.startsWith(prefix),
        );
        if (!exempt) expect(skin[name], name).toBeDefined();
      }
    }
  });

  it.each([
    ...TEXT_PAIRS.filter(([, background]) => !background.startsWith("color-admin")),
    ...TINT_PAIRS,
    ["color-on-ink", "color-text"],
    ["color-on-ink-muted", "color-text"],
  ] as [string, string][])("text %s on %s is readable (4.5:1)", (foreground, background) => {
    expect(contrast(skin[foreground], skin[background])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(CONTROL_PAIRS.filter(([, background]) => !background.startsWith("color-admin")))(
    "%s against %s is clearly visible (3:1)",
    (foreground, background) => {
      expect(contrast(skin[foreground], skin[background])).toBeGreaterThanOrEqual(3);
    },
  );

  it("draws its offset shadows in a deep green or grey, never plain black", () => {
    expect(skin["color-shade"]).not.toBe(skin["color-text"]);
    expect(skin["color-shade-soft"]).not.toBe(skin["color-text"]);
  });
});

describe("rows of buttons line up", () => {
  const rule = (selector: string) =>
    componentsCss.match(new RegExp(`\\n${selector.replace(".", "\\.")}\\s*\\{([^}]*)\\}`))?.[1] ??
    "";

  it("buttons in an action row never stretch to the height of a labelled field", () => {
    expect(rule(".page-actions")).toMatch(/align-items:\s*flex-end/);
  });

  it("toolbars and pagers keep every control on one centre line", () => {
    for (const selector of [".toolbar", ".toolbar__end", ".pager"]) {
      expect(rule(selector), selector).toMatch(/align-items:\s*center/);
    }
  });
});
