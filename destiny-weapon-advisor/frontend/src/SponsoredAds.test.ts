import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.restoreAllMocks();
});

const sampleAd = {
  offer_id: 1,
  headline: "Best Hand Cannon",
  blurb: "Upgrade your arsenal today",
  cta: "Shop Now",
  image_url: "https://example.com/img.jpg",
  click_url: "https://example.com/offer/1",
};

// ---------------------------------------------------------------------------
// fetchAds — happy path
// ---------------------------------------------------------------------------
describe("fetchAds — success", () => {
  it("returns the ads array from the API response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        json: async () => ({ ads: [sampleAd] }),
      }),
    );

    const { fetchAds } = await import("./api");
    const result = await fetchAds();

    expect(result).toHaveLength(1);
    expect(result[0].click_url).toBe("https://example.com/offer/1");
    expect(result[0].headline).toBe("Best Hand Cannon");
  });

  it("calls /api/ads with the n param", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ ads: [] }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { fetchAds } = await import("./api");
    await fetchAds(6);

    const [url] = mockFetch.mock.calls[0] as [string];
    expect(url).toContain("n=6");
  });

  it("returns empty array when ads key is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        json: async () => ({}),
      }),
    );

    const { fetchAds } = await import("./api");
    const result = await fetchAds();
    expect(result).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// fetchAds — error path (must never throw)
// ---------------------------------------------------------------------------
describe("fetchAds — error resilience", () => {
  it("resolves to [] when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    const { fetchAds } = await import("./api");
    const result = await fetchAds();
    expect(result).toEqual([]);
  });

  it("resolves to [] when response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ status: 500, ok: false }),
    );

    const { fetchAds } = await import("./api");
    const result = await fetchAds();
    expect(result).toEqual([]);
  });

  it("resolves to [] when json parsing throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        json: async () => { throw new Error("bad json"); },
      }),
    );

    const { fetchAds } = await import("./api");
    const result = await fetchAds();
    expect(result).toEqual([]);
  });
});
