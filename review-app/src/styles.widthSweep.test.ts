import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const stylesPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "styles.css",
);

const styles = readFileSync(stylesPath, "utf-8");

/**
 * Extract the body of a `@media (max-width: <px>)` block, then look up a
 * specific selector inside it. Returns the matched declaration block, or
 * `null` if either the media query or the selector is missing.
 */
function extractMediaRule(maxWidthPx: number, selector: string): string | null {
  const mediaPattern = new RegExp(
    `@media\\s*\\(\\s*max-width:\\s*${maxWidthPx}px\\s*\\)\\s*\\{`,
    "m",
  );
  const mediaMatch = mediaPattern.exec(styles);
  if (!mediaMatch) {
    return null;
  }

  let depth = 1;
  let cursor = mediaMatch.index + mediaMatch[0].length;
  const start = cursor;
  while (cursor < styles.length && depth > 0) {
    const char = styles[cursor];
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
    }
    cursor += 1;
  }
  const body = styles.slice(start, cursor - 1);

  const selectorPattern = new RegExp(`${selector}\\s*\\{([^}]*)\\}`, "m");
  const selectorMatch = body.match(selectorPattern);
  return selectorMatch ? selectorMatch[1] : null;
}

function extractRule(selector: string): string {
  const pattern = new RegExp(`${selector}\\s*\\{([^}]*)\\}`, "m");
  const match = styles.match(pattern);
  if (!match) {
    throw new Error(`Selector ${selector} not found in styles.css`);
  }
  return match[1];
}

/**
 * Width-sweep regression coverage. Vitest cannot run a real layout pass at
 * 1280 / 1440 / 1920 / 2560 / 5120 px (jsdom has no layout engine), so this
 * file pins the responsive contract by extracting the media-query bodies
 * straight out of `styles.css` and asserting each breakpoint still collapses
 * the grids it owns. A future change that drops a breakpoint or removes the
 * single-column fallback fails the build.
 */
describe("public route responsive width sweep", () => {
  describe("desktop (\u2265 1101px: 1280, 1440, 1920, 2560, 5120 px)", () => {
    it("keeps the hero as a 2-column grid (1.6fr / 22rem panel) at every desktop width", () => {
      const heroRule = extractRule("\\.hero");
      expect(heroRule).toMatch(
        /grid-template-columns:\s*minmax\(0,\s*1\.6fr\)\s+minmax\(min\(100%,\s*22rem\),\s*1fr\)/,
      );
    });

    it("keeps .public-briefing-drawer-grid as a 2-column rhythm at desktop widths", () => {
      const rule = extractRule("\\.public-briefing-drawer-grid");
      expect(rule).toMatch(/grid-template-columns:\s*repeat\(2,/);
    });

    it("keeps .security-status-grid stacked at desktop widths", () => {
      const rule = extractRule("\\.security-status-grid");
      expect(rule).toMatch(/grid-template-columns:\s*1fr/);
    });

    it("keeps .metrics-grid using auto-fit minmax for KPI strips at desktop widths", () => {
      const rule = extractRule("\\.metrics-grid");
      // Tile minimum stays auto-fit + at-least-260px so KPI strips never
      // collapse to a single column inside the wide content container.
      expect(rule).toMatch(/grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(/);
      expect(rule).toMatch(/260px/);
    });
  });

  describe("admin breakpoint (\u2264 1100px)", () => {
    it("collapses the admin shell layout to a single column", () => {
      const adminLayout = extractMediaRule(1100, "\\.admin-shell-layout");
      expect(adminLayout).not.toBeNull();
      expect(adminLayout!).toMatch(/grid-template-columns:\s*1fr/);
    });
  });

  describe("hero stack breakpoint (\u2264 960px)", () => {
    it("collapses .hero to one column so the headline and panel stack vertically", () => {
      const heroAtMobile = extractMediaRule(960, "\\.hero");
      expect(heroAtMobile).not.toBeNull();
      expect(heroAtMobile!).toMatch(/grid-template-columns:\s*1fr/);
    });
  });

  describe("workbench breakpoint (\u2264 900px)", () => {
    /**
     * The 900px block uses a single compound selector list
     * (`.product-shell-header, .admin-shell-layout, .hero, .metrics-grid,
     * .workbench-layout { grid-template-columns: 1fr; }`), so per-selector
     * extraction returns null. Instead, assert the compound rule itself is
     * present with the four targets we care about.
     */
    it("collapses hero/metrics/workbench grids to one column via the compound 900px rule", () => {
      const blockPattern =
        /@media\s*\(\s*max-width:\s*900px\s*\)\s*\{[\s\S]*?\}\s*\}/m;
      const blockMatch = blockPattern.exec(styles);
      expect(blockMatch).not.toBeNull();

      const block = blockMatch![0];
      for (const selector of [
        ".hero",
        ".metrics-grid",
        ".workbench-layout",
      ]) {
        expect(block).toContain(selector);
      }
      expect(block).toMatch(/grid-template-columns:\s*1fr/);
    });

    it("collapses .security-transparency-grid to one column at 900px", () => {
      const rule = extractMediaRule(900, "\\.security-transparency-grid");
      expect(rule).not.toBeNull();
      expect(rule!).toMatch(/grid-template-columns:\s*1fr/);
    });
  });

  describe("hero-panel column breakpoint (\u2264 720px)", () => {
    it("collapses .public-briefing-drawer-grid to one column on narrow viewports", () => {
      const rule = extractMediaRule(720, "\\.public-briefing-drawer-grid");
      expect(rule).not.toBeNull();
      expect(rule!).toMatch(/grid-template-columns:\s*1fr/);
    });
  });

  describe("phone breakpoint (\u2264 640px)", () => {
    it("declares a 640px block that collapses metric / showcase / status grids to one column", () => {
      const blockPattern =
        /@media\s*\(\s*max-width:\s*640px\s*\)\s*\{[\s\S]*?\n\}/m;
      const blockMatch = blockPattern.exec(styles);
      expect(blockMatch).not.toBeNull();

      const block = blockMatch![0];
      for (const selector of [
        ".metrics-grid",
        ".showcase-grid",
        ".security-status-grid",
      ]) {
        expect(block).toContain(selector);
      }
    });
  });
});
