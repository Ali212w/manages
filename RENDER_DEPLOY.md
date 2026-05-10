# Render.com Deployment Guide — manages

A practical, step-by-step guide for getting this project live on
[Render.com](https://render.com).

> All deployment files (`Procfile`, `runtime.txt`, `render.yaml`,
> `build.sh`) are already in this repo. The only things you need are:
> a GitHub account, a Render account, and a few credentials.

---

## 0 · What gets created

After you finish this guide you will have, on Render:

| Resource | What it is | Cost (estimate) |
|---|---|---|
| **Web Service** `manages-web` | The Flask app (Python 3.11, gunicorn + eventlet) | Standard plan = **$25 / month** (2 GB RAM — required for the heavy ML libs) |
| **PostgreSQL DB** `manages-db` | The application database | Render Free Postgres (auto-suspends after 90 days; upgrade to $7/mo for production) |
| **Persistent Disk** `manages-uploads` | 1 GB volume mounted at `app/static/uploads/` | $0.25 / GB / month ≈ **$0.25 / month** |
| Build Pipeline | Already chosen "Performance" in your workspace | Pay-per-minute (only consumes minutes during deploys) |

> Why **Standard, not Free/Starter** for the web service?
> The project bundles heavy ML libraries (`scikit-learn`, `numpy`,
> `pandas`, `moviepy`, `eventlet`, `openai`). The 512 MB Free/Starter
> tier almost always OOM-crashes during boot. 2 GB is the practical
> minimum.

---

## 1 · Push the project to GitHub

```bash
unzip manages_redesigned.zip -d manages
cd manages
git init && git checkout -b main
git add . && git commit -m "Initial commit"

# Create an empty repo on github.com first, then:
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

Make sure `.env` and `instance/` and `app.db` are NOT pushed (the
included `.gitignore` should handle this — double-check).

---

## 2 · One-click setup via Blueprint (the easy path)

1. Go to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub account (first time only) and pick the repo
   you just pushed.
4. Render reads `render.yaml` and shows you a preview of
   1 web service + 1 database + 1 disk. Click **Apply**.
5. Render starts:
   - Provisioning the Postgres DB
   - Running `./build.sh` (≈ 8–12 minutes the first time — those ML
     libs are big)
   - Booting `gunicorn` with the right worker class
   - Mounting the persistent disk at `app/static/uploads/`

When you see **Deploy live** (green dot), open the service URL — it
looks like `https://manages-web.onrender.com`.

---

## 3 · Fill the secret env vars

Render auto-generates `SECRET_KEY` and `JWT_SECRET_KEY`, and injects
`DATABASE_URL` from the Postgres add-on. The only ones **you** need to
fill (one-time, in the dashboard → service → Environment tab):

| Variable | Where to get it |
|---|---|
| `MAIL_USERNAME` | Your SMTP username (e.g. Gmail address) |
| `MAIL_PASSWORD` | SMTP App Password (Gmail: Account → Security → App passwords) |
| `MAIL_DEFAULT_SENDER` | The "From" address shown to recipients |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys (only needed if you use the AI features) |

After saving them, click **Manual Deploy → Deploy latest commit** so
the new env vars are picked up.

---

## 4 · Initialise the database (one time)

The first deploy already runs `flask db upgrade` for you (in
`build.sh`). If you want to seed admin data:

1. In the Render dashboard go to your web service → **Shell** tab
   (looks like a terminal icon).
2. Run any seeder scripts you have, e.g.:
   ```bash
   python seed_plans_usd.py
   ```

---

## 5 · Common problems & quick fixes

### Build fails with "MemoryError" / "killed"
You're on Free/Starter (512 MB). Upgrade the **web service** plan to
Standard ($25/mo, 2 GB) — easy switch in the dashboard. Build Pipeline
tier (the one in Workspace Settings) is unrelated.

### "could not translate host name 'localhost'" at runtime
Means a service is trying to connect to a local Redis / DB that
doesn't exist on Render. Make sure:
- `DATABASE_URL` is set (auto from the DB add-on)
- `REDIS_URL` is empty OR points at a real Render Redis instance

### File uploads disappear after redeploy
You skipped the persistent disk. Re-apply the Blueprint, or in the
service settings → **Disks**, add a 1 GB disk mounted at
`/opt/render/project/src/app/static/uploads`.

### `flask db upgrade` fails on first deploy
That's OK if you have no Alembic versions yet — `build.sh` swallows
the error. Once the DB exists, generate migrations locally
(`flask db init && flask db migrate`) then push.

### Static files (CSS / JS) load slowly
Flask serves them itself. Acceptable for a launch; later put
Cloudflare in front of the service URL or migrate static assets to a
CDN / S3.

### App is slow to wake up
Render web services on Free plans sleep after 15 min of inactivity.
On Standard or higher they stay warm.

---

## 6 · Going further

- **Background workers (Celery)** — add a separate `worker:` service in
  `render.yaml`. Costs another ~$25/month.
- **Redis (real)** — add a Render Redis add-on, set `REDIS_URL` env
  var on the web service.
- **Custom domain** — service → Settings → Custom Domains.
- **HTTPS** — automatic, no setup needed.

---

## 7 · Files relevant to this deploy

| File | What it does |
|---|---|
| `render.yaml` | Blueprint definition (services, DB, disk, env vars) |
| `Procfile` | Fallback start command (used when no `startCommand` in render.yaml) |
| `build.sh` | Run-once-per-deploy: pip install + db migrations |
| `runtime.txt` | Locks Python to 3.11.9 |
| `requirements.txt` | Adds `gunicorn` and `psycopg2-binary` for production |
| `config.py` | Auto-translates Render's `postgres://` URL to `postgresql://` |

Backend logic, models, routes, services, templates — none of these
were modified for the deploy; only deployment-specific files were
added.
