import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const stylesPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "styles.css",
);

const styles = readFileSync(stylesPath, "utf-8");

function extractRule(selector: string): string {
  const pattern = new RegExp(`${selector}\\s*\\{([^}]*)\\}`, "m");
  const match = styles.match(pattern);
  if (!match) {
    throw new Error(`Selector ${selector} not found in styles.css`);
  }
  return match[1];
}

describe(".public-top-nav stacking guarantees", () => {
  const rule = extractRule("\\.public-top-nav");

  it("stays sticky so it does not lose its stacking context when the hero scrolls beneath it", () => {
    expect(rule).toMatch(/position:\s*sticky/);
  });

  it("declares an opaque background so the route-theme hero glow cannot bleed through if backdrop-filter support is lost", () => {
    const backgroundMatch = rule.match(/background:\s*([^;]+);/);
    expect(backgroundMatch).not.toBeNull();

    const backgroundValue = backgroundMatch![1].trim();
    const rgbaAlphaMatch = backgroundValue.match(
      /rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*([0-9.]+)\s*\)/,
    );
    expect(rgbaAlphaMatch).not.toBeNull();

    const alpha = Number.parseFloat(rgbaAlphaMatch![1]);
    expect(alpha).toBeGreaterThanOrEqual(0.85);
  });

  it("uses a z-index high enough to sit above the hero panels on every public route", () => {
    const zIndexMatch = rule.match(/z-index:\s*(\d+)/);
    expect(zIndexMatch).not.toBeNull();

    const zIndex = Number.parseInt(zIndexMatch![1], 10);
    expect(zIndex).toBeGreaterThanOrEqual(50);
  });
});
