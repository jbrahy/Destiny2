import { describe, expect, it } from "vitest";
import { canonicalUrl, SITE } from "./url";
import { websiteJsonLd, weaponJsonLd } from "./jsonld";

describe("canonicalUrl", () => {
  it('returns site root for "/"', () => {
    expect(canonicalUrl("/")).toBe("https://destinyopt.com/");
  });

  it("returns full URL for a path", () => {
    expect(canonicalUrl("/weapons/x")).toBe("https://destinyopt.com/weapons/x");
  });

  it("does not produce double slashes", () => {
    const result = canonicalUrl("/weapons/x");
    expect(result).not.toContain("//weapons");
    expect(result.replace("https://", "")).not.toContain("//");
  });
});

describe("websiteJsonLd", () => {
  it('has @type === "WebSite"', () => {
    expect(websiteJsonLd()["@type"]).toBe("WebSite");
  });

  it("has url equal to SITE", () => {
    expect(websiteJsonLd().url).toBe(SITE);
  });

  it('has @context === "https://schema.org"', () => {
    expect(websiteJsonLd()["@context"]).toBe("https://schema.org");
  });
});

describe("weaponJsonLd", () => {
  it("has the weapon name", () => {
    expect(weaponJsonLd({ name: "Foo" }).name).toBe("Foo");
  });

  it('has @type set', () => {
    expect(weaponJsonLd({ name: "Foo" })["@type"]).toBeTruthy();
  });

  it("passes through optional type and element", () => {
    const result = weaponJsonLd({ name: "Bar", type: "Auto Rifle", element: "Solar" });
    expect(result.name).toBe("Bar");
  });
});
