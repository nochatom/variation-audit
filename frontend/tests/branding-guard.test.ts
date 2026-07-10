/**
 * Frontend branding regression guard.
 *
 * Static source-inspection tests (no rendering, no DOM) that catch the
 * exact class of bug found and fixed in this session: the same "V" text
 * placeholder silently re-implemented in 10 different files instead of
 * using components/ui/Logo.tsx, a missing favicon, and a stale page title.
 * These tests read source files directly and fail loudly if that pattern
 * reappears — they do not change any UI behavior.
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "..");
const LOGO_COMPONENT = path.join(ROOT, "components/ui/Logo.tsx");
const ICON_SVG = path.join(ROOT, "app/icon.svg");
const LAYOUT_TSX = path.join(ROOT, "app/layout.tsx");

const SCAN_DIRS = ["app", "components"];
const IGNORE_DIR_NAMES = new Set(["node_modules", ".next", ".git"]);

/** All .ts/.tsx source files under app/ and components/, as absolute paths. */
function walkSourceFiles(): string[] {
  const files: string[] = [];
  function walk(dir: string) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (IGNORE_DIR_NAMES.has(entry.name)) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (/\.(ts|tsx)$/.test(entry.name)) {
        files.push(full);
      }
    }
  }
  for (const dir of SCAN_DIRS) {
    const abs = path.join(ROOT, dir);
    if (fs.existsSync(abs)) walk(abs);
  }
  return files;
}

const sourceFiles = walkSourceFiles();
const nonLogoFiles = sourceFiles.filter((f) => f !== LOGO_COMPONENT);

describe("branding regression guard", () => {
  it("components/ui/Logo.tsx exists and exports LogoMark", () => {
    expect(fs.existsSync(LOGO_COMPONENT)).toBe(true);
    const source = fs.readFileSync(LOGO_COMPONENT, "utf-8");
    expect(source).toMatch(/export function LogoMark\s*\(/);
  });

  it("no other file under app/ or components/ defines a component named *Logo*", () => {
    // Catches a second/competing logo implementation being added anywhere
    // else in the tree (the exact failure mode this guard exists for).
    const offenders: string[] = [];
    for (const file of nonLogoFiles) {
      const source = fs.readFileSync(file, "utf-8");
      if (/export\s+(default\s+)?function\s+\w*Logo\w*\s*\(/.test(source)) {
        offenders.push(path.relative(ROOT, file));
      }
    }
    expect(offenders).toEqual([]);
  });

  it("no file defines a *.tsx/*.ts sibling named Logo outside components/ui/", () => {
    const offenders = sourceFiles
      .filter((f) => /logo/i.test(path.basename(f)))
      .filter((f) => f !== LOGO_COMPONENT)
      .map((f) => path.relative(ROOT, f));
    expect(offenders).toEqual([]);
  });

  it('detects no standalone "V" brand-mark placeholder outside Logo.tsx', () => {
    // The exact bug this guard was written for: a <span>/<div> styled like
    // the navy icon container but containing a literal "V" character
    // instead of LogoMark's real SVG glyph. Matches both the current
    // (bg-ip-navy-fill) and the older, since-removed (bg-primary) variants
    // so this also guards against reverting to the legacy token.
    const placeholderPattern =
      /place-items-center[^"]*rounded-md[^"]*bg-(ip-navy-fill|primary)[^"]*"[^>]*>\s*V\s*</;
    const offenders: string[] = [];
    for (const file of nonLogoFiles) {
      const source = fs.readFileSync(file, "utf-8");
      if (placeholderPattern.test(source)) {
        offenders.push(path.relative(ROOT, file));
      }
    }
    expect(offenders).toEqual([]);
  });

  it("brand-mark SVG path data appears only inside Logo.tsx, nowhere else", () => {
    // A second file hand-copying the raw path data (rather than importing
    // LogoMark) would defeat the whole point of having one canonical
    // component — this catches that even if it doesn't match the "V"
    // placeholder pattern above.
    const BRAND_PATH_FRAGMENTS = [
      "M24,24 L50,72 L76,24", // the V glyph, as used in LogoMark
      "M50,27.5 C50.975,28.475", // the sparkle, as used in LogoMark
    ];
    const offenders: string[] = [];
    for (const file of nonLogoFiles) {
      const source = fs.readFileSync(file, "utf-8");
      if (BRAND_PATH_FRAGMENTS.some((fragment) => source.includes(fragment))) {
        offenders.push(path.relative(ROOT, file));
      }
    }
    expect(offenders).toEqual([]);
  });

  it("every page that links to VariationIQ home imports LogoMark from the canonical path", () => {
    // Positive check, not just a negative one: everywhere a
    // aria-label="VariationIQ home" link exists, it must actually import
    // and use the canonical component, not just avoid the old placeholder.
    const offenders: string[] = [];
    for (const file of nonLogoFiles) {
      const source = fs.readFileSync(file, "utf-8");
      if (source.includes('aria-label="VariationIQ home"')) {
        const importsLogoMark = /from\s+["']@\/components\/ui\/Logo["']/.test(source);
        const usesLogoMark = /<LogoMark\b/.test(source);
        if (!importsLogoMark || !usesLogoMark) {
          offenders.push(path.relative(ROOT, file));
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("app/icon.svg exists and is a well-formed SVG", () => {
    expect(fs.existsSync(ICON_SVG)).toBe(true);
    const content = fs.readFileSync(ICON_SVG, "utf-8").trim();
    expect(content.startsWith("<svg")).toBe(true);
    expect(content).toContain("</svg>");
  });

  it("page metadata title uses VariationIQ, not the old product name", () => {
    const source = fs.readFileSync(LAYOUT_TSX, "utf-8");
    const match = source.match(/title:\s*"([^"]+)"/);
    expect(match, "expected a title: \"...\" entry in app/layout.tsx metadata").not.toBeNull();
    expect(match![1]).toContain("VariationIQ");
    expect(match![1]).not.toBe("Variation Audit");
  });
});
