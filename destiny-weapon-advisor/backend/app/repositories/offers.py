from app import db

_COLS = (
    "offer_id", "name", "category", "advertiser", "countries",
    "payout_type", "payout_amount", "tracking_url", "headline",
    "blurb", "cta", "image_url", "status",
)


def _row_to_dict(row):
    return dict(zip(_COLS, row))


async def upsert(pool, offer: dict) -> None:
    """Insert or update an offer by offer_id."""
    await db.execute(
        pool,
        "INSERT INTO offers "
        "(offer_id, name, category, advertiser, countries, payout_type, payout_amount, "
        "tracking_url, headline, blurb, cta, image_url, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "name=VALUES(name), category=VALUES(category), advertiser=VALUES(advertiser), "
        "countries=VALUES(countries), payout_type=VALUES(payout_type), "
        "payout_amount=VALUES(payout_amount), tracking_url=VALUES(tracking_url), "
        "headline=VALUES(headline), blurb=VALUES(blurb), cta=VALUES(cta), "
        "image_url=VALUES(image_url), status=VALUES(status)",
        (
            offer["offer_id"],
            offer["name"],
            offer.get("category", ""),
            offer.get("advertiser", ""),
            offer.get("countries", ""),
            offer.get("payout_type", ""),
            offer.get("payout_amount", 0),
            offer["tracking_url"],
            offer["headline"],
            offer["blurb"],
            offer["cta"],
            offer.get("image_url"),
            offer.get("status", "active"),
        ),
    )


async def list_random_active(pool, n: int) -> list[dict]:
    """Return up to n active offers in random order."""
    rows = await db.fetchall(
        pool,
        "SELECT offer_id, name, category, advertiser, countries, payout_type, payout_amount, "
        "tracking_url, headline, blurb, cta, image_url, status "
        "FROM offers WHERE status='active' ORDER BY RAND() LIMIT %s",
        (n,),
    )
    return [_row_to_dict(r) for r in rows]


async def get_active(pool, offer_id: int) -> dict | None:
    """Return an active offer by offer_id, or None."""
    row = await db.fetchone(
        pool,
        "SELECT offer_id, name, category, advertiser, countries, payout_type, payout_amount, "
        "tracking_url, headline, blurb, cta, image_url, status "
        "FROM offers WHERE offer_id=%s AND status='active'",
        (offer_id,),
    )
    return _row_to_dict(row) if row is not None else None


async def pause_missing(pool, keep_ids: list[int]) -> int:
    """Set status='paused' for active offers not in keep_ids. Returns rowcount."""
    if not keep_ids:
        return await db.execute(
            pool,
            "UPDATE offers SET status='paused' WHERE status='active'",
            (),
        )
    placeholders = ",".join(["%s"] * len(keep_ids))
    return await db.execute(
        pool,
        f"UPDATE offers SET status='paused' WHERE status='active' AND offer_id NOT IN ({placeholders})",
        tuple(keep_ids),
    )


async def log_click(pool, offer_id: int, user_id: int) -> None:
    """Record an ad click."""
    await db.execute(
        pool,
        "INSERT INTO ad_clicks (offer_id, user_id) VALUES (%s, %s)",
        (offer_id, user_id),
    )
