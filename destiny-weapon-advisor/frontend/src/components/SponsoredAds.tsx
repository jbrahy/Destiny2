import { useEffect, useState } from "react";
import { Ad, fetchAds } from "../api";

export function SponsoredAds({ section }: { section: string }) {
  const [ads, setAds] = useState<Ad[]>([]);

  useEffect(() => {
    fetchAds(4).then(setAds);
  }, [section]);

  if (ads.length === 0) return null;

  return (
    <section
      aria-label="Sponsored"
      style={{
        marginTop: 32,
        padding: "16px 0",
        borderTop: "1px solid #333",
      }}
    >
      <p
        style={{
          margin: "0 0 12px 0",
          fontSize: 11,
          color: "#888",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        Sponsored
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: 16,
        }}
      >
        {ads.map((ad) => (
          <div
            key={ad.offer_id}
            style={{
              background: "#1a1a2e",
              border: "1px solid #2a2a4a",
              borderRadius: 8,
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {ad.image_url && (
              <img
                src={ad.image_url}
                alt=""
                style={{
                  width: "100%",
                  borderRadius: 4,
                  objectFit: "cover",
                  maxHeight: 120,
                }}
              />
            )}
            <p style={{ margin: 0, fontWeight: "bold", fontSize: 14, color: "#e0e0e0" }}>
              {ad.headline}
            </p>
            <p style={{ margin: 0, fontSize: 12, color: "#aaa", lineHeight: 1.4 }}>
              {ad.blurb}
            </p>
            <a
              href={ad.click_url}
              target="_blank"
              rel="noopener sponsored"
              style={{
                display: "inline-block",
                marginTop: "auto",
                padding: "6px 12px",
                background: "#4a4aff",
                color: "#fff",
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 600,
                textDecoration: "none",
                textAlign: "center",
              }}
            >
              {ad.cta}
            </a>
          </div>
        ))}
      </div>
    </section>
  );
}
