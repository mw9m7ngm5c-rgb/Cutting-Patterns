# Running the app in the cloud

This puts the app on a server on the internet, so you and a few colleagues can use it from any
browser (office, home, phone) at an address like `https://cutting-patterns.onrender.com`. Everyone
signs in with their own user name and password.

The guide uses [Render](https://render.com), because it builds straight from the GitHub repository,
gives the app https automatically and keeps the database on a disk that survives restarts and updates.
The app is packaged as a Docker image (`Dockerfile`), so any host that runs a Docker container with a
persistent folder also works (Fly.io, Railway, a small VPS); see "Other hosts" at the end.

## What it costs

On Render: the **Starter** instance (about US$7 a month) plus a 1 GB disk (about US$0.25 a month).
The free plan cannot be used because it has no disk: the database would be wiped on every restart.
Check Render's pricing page for current prices.

1 GB holds a great many datasets and runs. Pattern searches use the instance's processor; on Starter
they run, but more slowly than on a desktop Mac. If searches feel slow, move to a larger instance in
the service's settings; nothing else changes.

## Set it up (once, about 15 minutes)

1. Create an account at render.com and sign in with GitHub. Allow Render to see the
   `cutting-patterns` repository.
2. In Render choose **New → Blueprint**, pick the repository and the `main` branch. Render reads
   `render.yaml` and proposes one web service, `cutting-patterns`, with a disk.
3. Render asks for two values:
   - `CP_ADMIN_USER`: your user name, for example `anna`.
   - `CP_ADMIN_PASSWORD`: your first password, at least 8 characters. You can change it in the app
     afterwards.
   
   `CP_SECRET_KEY` is filled in by Render with a random value. Leave it alone: it signs the login
   cookie, and changing it signs everyone out.
4. Choose **Apply**. The first build takes a few minutes. When the service shows **Live**, open the
   address Render shows at the top of the service page.
5. Sign in with the user name and password from step 3.
6. Import your Simsaw dataset on the **Datasets** page (upload the `.mdb` file), exactly as on a Mac.

If you would rather use your own address (for example `patterns.thorpetimbers.co.za`), add it under
the service's **Settings → Custom Domains** and follow Render's instructions for the DNS record.

## Adding colleagues

Signed in as an administrator, click your name at the top right (the **Your account** page):

- **Add someone**: a user name and a first password. Tick *Administrator* only for people who should
  be able to add others and download backups. Tell them the password yourself; nothing is emailed.
- **Set password**: gives someone a new password when they forget theirs.
- **Remove**: takes away someone's access. Their work stays.

Everyone can change their own password on the same page. Everyone sees and can change the same
datasets, as on the office Mac: this is a shared workspace, not separate private ones.

A sign-in lasts 12 hours, then the app asks again. Each wrong password makes the app wait a second before answering, which makes guessing slow.

## Backups

Render keeps daily snapshots of the disk for a few days (see the disk section of the service). On top
of that, download your own copy from time to time, for example every Friday:

**Your account → Download a backup** (administrators only). The file is a complete copy of every
dataset, run and pattern search, taken safely while the app runs. Keep it with your other company
files. The same file opens on a Mac install of the app (`python -m app --db the-file.db`).

### Putting a backup back

1. Copy the backup file onto the server's disk, into `/data`. Render's **SSH** documentation explains
   how to connect to the service and copy a file to it (`scp`).
2. In the service's **Shell** tab (or over SSH) run:

   ```
   python -m app restore /data/cutting_patterns-2026-01-31-180000.db
   ```

   The data it replaces is first saved under `/data/backups/`, so a restore can itself be undone.
   The app keeps running; reload the page.

## Updates

The service redeploys by itself whenever `main` changes on GitHub (for example when a pull request is
merged). The database is on the disk, so updates never touch your data; any database changes a new
version needs are applied when it starts. Watch the deploy in the service's **Events** tab. To deploy
by hand, use **Manual Deploy → Deploy latest commit**.

## Good to know

- **One instance only.** The database is a single SQLite file on one disk, so the service must not
  be scaled to more than one instance. `render.yaml` sets this up correctly; do not turn on
  autoscaling.
- **Moving from the office Mac.** Take a backup on the Mac (`./deploy/macos/backup-now.sh`), then
  restore it on the server as described above. From then on use only the cloud copy, or the two will
  drift apart.
- **Health check.** `/healthz` answers without signing in; Render uses it to know the app is up.
- The app only ever sends pages to people who are signed in. Data does not leave the server except
  through the backup download and the Excel exports people choose to download.

## Settings the server reads

| Variable | What it does | Set by |
|---|---|---|
| `CP_ADMIN_USER`, `CP_ADMIN_PASSWORD` | First administrator, created at start-up if no account has that name. Later changes do not alter existing accounts. | you, once |
| `CP_SECRET_KEY` | Signs the login cookie. | Render (random) |
| `CP_REQUIRE_LOGIN=1` | Always ask for a sign-in, even before any account exists. | Dockerfile |
| `CP_DB` | Database file, `/data/cutting_patterns.db`. | Dockerfile |
| `CP_BEHIND_PROXY=1` | Trust the host's https forwarding, so the login cookie is marked secure. | Dockerfile |
| `PORT`, `CP_HOST` | Where the app listens. | host / Dockerfile |

## Other hosts

Any host that runs the `Dockerfile` works if you give it:

- a persistent volume mounted at `/data`,
- the variables `CP_SECRET_KEY` (a long random string), `CP_ADMIN_USER` and `CP_ADMIN_PASSWORD`,
- https in front of it (most hosts provide this),
- a single instance.

To try the image on your own computer:

```
docker build -t cutting-patterns .
docker run -p 8000:8000 -v cp-data:/data \
  -e CP_SECRET_KEY=change-me -e CP_ADMIN_USER=anna -e CP_ADMIN_PASSWORD=first-password \
  -e CP_BEHIND_PROXY=0 cutting-patterns
```

then open http://localhost:8000.

Accounts work on the Mac install too: `python -m app adduser anna --admin` turns on sign-in there.
