from urllib.parse import urlencode

import httpx

from app.config import Settings

AUTHORIZE_URL = "https://www.bungie.net/en/OAuth/Authorize"
TOKEN_URL = "https://www.bungie.net/Platform/App/OAuth/Token/"


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": redirect_uri,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


async def _post_token(data: dict, settings: Settings, client: httpx.AsyncClient) -> dict:
    resp = await client.post(
        TOKEN_URL,
        data=data,
        auth=(settings.bungie_client_id, settings.bungie_client_secret),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-API-Key": settings.bungie_api_key,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def exchange_code(code: str, settings: Settings, client: httpx.AsyncClient) -> dict:
    return await _post_token(
        {"grant_type": "authorization_code", "code": code}, settings, client
    )


async def refresh_tokens(refresh_token: str, settings: Settings, client: httpx.AsyncClient) -> dict:
    return await _post_token(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}, settings, client
    )
