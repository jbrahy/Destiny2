import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// Mock window.location so we can spy on href assignments without JSDOM errors
// ---------------------------------------------------------------------------
let hrefAssigned: string | undefined;

beforeEach(() => {
  hrefAssigned = undefined;
  Object.defineProperty(window, "location", {
    value: { href: "" },
    writable: true,
    configurable: true,
  });
  Object.defineProperty(window.location, "href", {
    get: () => hrefAssigned ?? "",
    set: (v: string) => { hrefAssigned = v; },
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// 401 → redirect
// ---------------------------------------------------------------------------
describe("apiFetch — 401 handling", () => {
  it("redirects to /api/login on a 401 response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401, ok: false }));

    // Import fresh each time so the module-level fetch mock is applied
    const { fetchWeapons } = await import("./api");
    await fetchWeapons().catch(() => {/* expected rejection */});

    expect(hrefAssigned).toBe("/api/login");
  });
});

// ---------------------------------------------------------------------------
// CSRF header on mutating requests
// ---------------------------------------------------------------------------
describe("apiFetch — CSRF header", () => {
  it("sends X-CSRF-Token from the csrftoken cookie on POST requests", async () => {
    // Arrange: set the cookie before the call
    Object.defineProperty(document, "cookie", {
      value: "csrftoken=abc123",
      writable: true,
      configurable: true,
    });

    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { selectMembership } = await import("./api");
    await selectMembership(1, "member-1").catch(() => {/* ignore */});

    const [_url, opts] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = opts.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("abc123");
  });

  it("sends credentials: same-origin on mutating requests", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { selectMembership } = await import("./api");
    await selectMembership(1, "member-2").catch(() => {/* ignore */});

    const [_url, opts] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(opts.credentials).toBe("same-origin");
  });
});

// ---------------------------------------------------------------------------
// getCookie helper (exported for tests)
// ---------------------------------------------------------------------------
describe("getCookie", () => {
  it("parses a named cookie from document.cookie", async () => {
    Object.defineProperty(document, "cookie", {
      value: "foo=bar; csrftoken=tok123; baz=qux",
      writable: true,
      configurable: true,
    });
    const { getCookie } = await import("./api");
    expect(getCookie("csrftoken")).toBe("tok123");
    expect(getCookie("foo")).toBe("bar");
    expect(getCookie("missing")).toBeUndefined();
  });
});
