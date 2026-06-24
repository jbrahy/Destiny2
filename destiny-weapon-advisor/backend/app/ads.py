from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from app.auth import get_current_user
from app.deps import get_pool
from app.repositories import offers

router = APIRouter()


@router.get("/api/ads")
async def get_ads(n: int = 4, current_user: dict = Depends(get_current_user), pool=Depends(get_pool)) -> dict:
    n = max(1, min(n, 8))
    rows = await offers.list_random_active(pool, n)
    return {"ads": [{"offer_id": r["offer_id"], "headline": r["headline"], "blurb": r["blurb"],
                     "cta": r["cta"], "image_url": r["image_url"],
                     "click_url": f"/api/ads/{r['offer_id']}/click"} for r in rows]}


@router.get("/api/ads/{offer_id}/click")
async def click_ad(offer_id: int, current_user: dict = Depends(get_current_user), pool=Depends(get_pool)) -> RedirectResponse:
    offer = await offers.get_active(pool, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    await offers.log_click(pool, offer_id, current_user["user_id"])
    return RedirectResponse(offer["tracking_url"], status_code=302)
