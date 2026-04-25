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

describe("hero left-column vertical alignment", () => {
  it("vertically centers .public-hero-copy so a tall right panel does not strand the headline at the top", () => {
    expect(extractRule("\\.public-hero-copy")).toMatch(/justify-content:\s*center/);
  });

  it("vertically centers .security-hero-copy for the same reason on the security route", () => {
    expect(extractRule("\\.security-hero-copy")).toMatch(/justify-content:\s*center/);
  });

  it("stretches .hero-wide rows so the copy column can match the panel height", () => {
    expect(extractRule("\\.hero-wide")).toMatch(/align-items:\s*stretch/);
  });

  it("vertically centers the first child of every .hero-wide so non-public routes (like /demo) match the public/security pattern", () => {
    expect(extractRule("\\.hero-wide > :first-child")).toMatch(
      /justify-content:\s*center/,
    );
  });
});
