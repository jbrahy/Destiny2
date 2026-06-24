# Production Deploy (D) — Design Spec

**Sub-project:** D (final of program C → A → B → E → D).
**Date:** 2026-06-23
**Status:** Approved design — pending implementation plan
**Deploys:** sub-projects A (multi-user app), B (ads), E1+E2 (SEO foundation) to **destinyopt.com**.

---

## 1. Goal

Make the site live at `https://destinyopt.com`: the prerendered public content + ads served by nginx with TLS, the FastAPI app (multi-user, Bungie SSO) behind it, MySQL 8 on-box, secrets from SSM, on a single already-provisioned EC2 — via an idempotent, re-runnable deploy.

**Non-goals (follow-ups):** S3 DB backups, CI/CD automation, multi-box/autoscaling, CDN.

---

## 2. Target & decisions locked
- **Host:** EC2 `<EC2_INSTANCE_ID>`, `t4g.large` (Amazon Linux, ARM/aarch64), us-east-1a; already has SSM agent + `<DEPLOY_USER>` sudo + SSH key.
- **MySQL:** on-box MySQL 8 (aarch64).
- **IP/DNS:** allocate an Elastic IP, associate it, repoint Route53 (zone `<ROUTE53_ZONE_ID>`) A records (`destinyopt.com` + `www`) to it.
- **Secrets:** AWS SSM Parameter Store (SecureString) → rendered to a systemd EnvironmentFile.
- **TLS:** Let's Encrypt (certbot, nginx plugin).

## 3. ⚠️ Irreversible / outward-facing steps — require explicit confirmation at execution
1. Allocate + associate Elastic IP (changes the box's public IP).
2. Repoint Route53 A records to the EIP.
3. Issue the Let's Encrypt cert (public ACME challenge).
4. First production service start (site goes live).
Each is confirmed with the user immediately before running — not fired autonomously.

## 4. 👤 User-only steps (cannot be automated)
- **Bungie OAuth app** (bungie.net/en/Application): set Redirect URL = `https://destinyopt.com/callback`, OAuth Client Type = **Confidential**. Login fails until done. Required before the login smoke test.
- Confirm the registrar/NS delegates `destinyopt.com` to the Route53 zone (DNS already resolves, so this appears done — verify).

---

## 5. Architecture

```
Internet → nginx (:443 TLS, :80 redirect)
  /                      → dist/index.html (prerendered landing)
  /weapons/<slug>        → try_files $uri $uri.html  (flat prerendered HTML)
  /assets/ /robots.txt /sitemap.xml → static from dist/
  /app, /app/*           → try_files $uri /index.html  (SPA fallback; client renders AppShell)
  /api/* /auth/* /callback → proxy_pass http://127.0.0.1:8000  (uvicorn)
uvicorn (systemd, 127.0.0.1:8000) → FastAPI app (EnvironmentFile from SSM)
                                   → MySQL 8 (localhost)
```

Document root: the built `destiny-weapon-advisor/frontend/dist`. App code under a deploy dir (e.g. `/opt/destiny/Destiny2`).

---

## 6. Components

### 6.1 Networking (`scripts/deploy/01_network.sh` — controller-run, AWS CLI)
- `aws ec2 allocate-address` → EIP; `associate-address` to the instance.
- Update Route53 A records (`destinyopt.com`, `www.destinyopt.com`) → EIP (UPSERT, TTL 300).
- Ensure SG `<SECURITY_GROUP_ID>` allows inbound 80 + 443 from `0.0.0.0/0` (22 already restricted; keep it).

### 6.2 Host packages (on box, via SSM)
- nginx, certbot + python3-certbot-nginx, MySQL 8 server (aarch64), Node 20 (for the frontend build), Python 3.11+ (verify the box's default `python3`; install `python3.11` if the default is older — the backend requires ≥3.11), git.

### 6.3 MySQL 8 (on box)
- Install, enable, `mysql_secure`-equivalent (set root pw from SSM), bind `127.0.0.1`.
- Create DB `advisor` (utf8mb4) + user `advisor`@`localhost` with the SSM password; grant on `advisor.*`.

### 6.4 Secrets (SSM → EnvironmentFile)
- Params (SecureString) under `/destinyopt/prod/`: `BUNGIE_API_KEY`, `BUNGIE_CLIENT_ID`, `BUNGIE_CLIENT_SECRET`, `DB_PASSWORD`, `TOKEN_ENC_KEY`, `SESSION_SECRET`. (Created once by the controller from the existing dev values / freshly generated keys — TOKEN_ENC_KEY/SESSION_SECRET generated fresh for prod.)
- IAM: attach a scoped policy to the instance role `AmazonSSMManagedInstanceCore_Role` allowing `ssm:GetParameters` on `arn:aws:ssm:us-east-1:<AWS_ACCOUNT_ID>:parameter/destinyopt/prod/*` + `kms:Decrypt` on the default SSM key.
- `scripts/deploy/render_env.sh` (on box): `aws ssm get-parameters --with-decryption` → write `/etc/destiny/advisor.env` (root, 0600) with the secrets plus non-secret config: `DB_HOST=127.0.0.1 DB_PORT=3306 DB_USER=advisor DB_NAME=advisor COOKIE_SECURE=true SESSION_TTL_DAYS=30 USER_CACHE_TTL_SECONDS=300 BUNGIE_THROTTLE_CONCURRENCY=20 REDIRECT_URI=https://destinyopt.com/callback FRONTEND_URL=https://destinyopt.com`.

### 6.5 Backend service (systemd)
- `/etc/systemd/system/destiny-advisor.service`: `ExecStart=<venv>/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`, `WorkingDirectory=/opt/destiny/Destiny2/destiny-weapon-advisor/backend`, `EnvironmentFile=/etc/destiny/advisor.env`, `Restart=always`, dedicated `User`. Lifespan runs migrations on start; deploy also runs `python -m scripts.import_offers`.

### 6.6 nginx + TLS
- `/etc/nginx/conf.d/destinyopt.conf` per §5 routing. `certbot --nginx -d destinyopt.com -d www.destinyopt.com` provisions + auto-renews; HTTP→HTTPS redirect. gzip on; cache headers for `/assets/`.

### 6.7 Deploy script (`scripts/deploy.sh`, on box, idempotent)
Order: `git pull` (in `/opt/destiny/Destiny2`) → `render_env.sh` → backend venv `pip install -e .` + `python -m scripts.migrate` + `python -m scripts.import_offers` → frontend `npm ci && npm run build` (content→SSG→sitemap; uses BUNGIE_API_KEY from env) → `systemctl restart destiny-advisor` → `nginx -t && systemctl reload nginx`. Re-runnable for every release.

---

## 7. Error handling / rollback
- Pre-migrate `mysqldump` to `/opt/destiny/backups/<ts>.sql`; keep the previous `dist/` as `dist.prev`.
- Deploy script `set -euo pipefail`; on failure it stops before swapping nginx (build into a temp dir, swap only on success).
- Rollback: restore `dist.prev`, `git checkout <prev>`, restart service; restore DB dump if a migration broke.
- certbot failure → site stays on HTTP (don't half-apply TLS); retry.

## 8. Testing / verification (post-deploy smoke — `scripts/deploy/smoke.sh`)
- `curl -sI https://destinyopt.com/` → 200; body contains the landing + one `<title>`.
- `curl -s https://destinyopt.com/weapons/<slug>` → 200 prerendered HTML w/ weapon name + canonical.
- `curl -s https://destinyopt.com/robots.txt` and `/sitemap.xml` → present, correct host.
- `curl -s https://destinyopt.com/api/health` → `{"status":"ok"}` (proxy works).
- `https://destinyopt.com/app` → loads (login gate).
- TLS: valid cert, HTTP→HTTPS redirect (`curl -sI http://destinyopt.com/` → 301 https).
- **Manual (after Bungie OAuth update):** full sign-in flow end-to-end → dashboard loads with the user's data; an ad CTA redirects through `/api/ads/<id>/click`.

## 9. Scope
**In:** EIP+DNS, SG 80/443, host packages, MySQL 8, SSM secrets+IAM, EnvironmentFile render, systemd service, nginx+TLS, idempotent deploy script, smoke + rollback. **Out:** S3 backups, CI/CD, multi-box, CDN (follow-ups). Also carries the E/A/B deferred cleanups opportunistically only if trivial (e.g., remove dead `App.tsx`) — otherwise left as logged follow-ups.
