from fastapi import FastAPI

app = FastAPI(title="Destiny 2 Weapon Advisor")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    import uvicorn

    from app.certs import ensure_self_signed_cert

    cert_path, key_path = ensure_self_signed_cert(".certs")
    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=8443,
        ssl_certfile=cert_path,
        ssl_keyfile=key_path,
    )


if __name__ == "__main__":
    run()
