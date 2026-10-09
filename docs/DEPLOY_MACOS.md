# Running the sawing-pattern app on a Mac

One Mac in the office runs the app in the background. Anyone on the office network opens it in a
browser. The data lives in one file on that Mac, backed up every evening.

Allow about half an hour. You need an administrator password for the first step only.

## 1. Install Python (once)

The Python that comes with macOS is too old.

1. Download the latest **Python 3.12 or 3.13** "macOS 64-bit universal2 installer" from
   https://www.python.org/downloads/macos/ and run it.
2. When it finishes, the installer opens a folder. Double-click **Install Certificates.command** in it.

If the Mac has Homebrew, `brew install python@3.12` does the same job.

## 2. Get the app

Open **Terminal** (Applications › Utilities) and run:

```
cd ~
git clone https://github.com/mw9m7ngm5c-rgb/Cutting-Patterns.git
cd Cutting-Patterns
```

If macOS offers to install the "command line developer tools" for `git`, accept and run the command again.
(Without git you can download the ZIP from GitHub and unzip it into your home folder instead, but then
updates are by hand; see step 8.)

## 3. Install

Still in Terminal, in the `Cutting-Patterns` folder:

```
./deploy/macos/install.sh
```

It creates a private Python environment in `.venv`, installs what the app needs and creates the
database `data/cutting_patterns.db`. It is safe to run again.

## 4. Try it

```
.venv/bin/python -m app
```

The browser opens the app. Import your Simsaw dataset from the Datasets page (or start a new one), have a
look around, then press Ctrl+C in Terminal to stop it.

## 5. Run it for the whole office

```
./deploy/macos/start-at-login.sh --shared
```

From now on the app runs in the background whenever this Mac user is logged in, restarts itself if it
ever stops, and backs up the database every day at 19:00. The script prints the address to give
everyone, for example `http://192.168.1.20:8000`.

- If macOS asks whether **Python** may accept incoming connections, click **Allow**.
- Without `--shared`, only this Mac can open the app (http://127.0.0.1:8000).
- Other options: `--port 8000`, `--backup-time 19:00`, `--keep 30` (backups kept). Run the script again
  to change them.

## 6. Keep the Mac available

The app is only reachable while this Mac is awake and this user is logged in.

- **Don't let it sleep:** System Settings › Energy (or Battery › Options on a laptop): turn on
  "Prevent automatic sleeping when the display is off". The screen may still turn off.
- **After a power cut:** in the same place, turn on "Start up automatically after a power failure".
  Then either log in after a restart, or turn on automatic login for this user (System Settings ›
  Users & Groups; not available while FileVault is on).
- **Keep its address:** ask whoever looks after the router to reserve this Mac's address (a "DHCP
  reservation"), so the link people use does not change.

## 7. Backups

- Every evening a copy goes into `~/Cutting-Patterns/backups/`, named by date and time. The newest 30
  are kept. Copies are safe to take while people are using the app.
- Back up now: `./deploy/macos/backup-now.sh`
- Those copies sit on the same Mac. Make sure the Mac itself is backed up too (Time Machine, or copy the
  `backups` folder to a server or cloud drive), or a dead disk takes everything with it.

**To restore a backup:**

```
./deploy/macos/stop.sh
cp backups/cutting_patterns-2026-10-09-190000.db data/cutting_patterns.db     # the copy you want
rm -f data/cutting_patterns.db-wal data/cutting_patterns.db-shm
./deploy/macos/start-at-login.sh --shared
```

## 8. Updating to a new version

```
./deploy/macos/update.sh
```

It backs up the database first, fetches the new version, updates the packages and the database, and
restarts the app. Your data is kept.

If you installed from a ZIP, instead: stop the app (`./deploy/macos/stop.sh`), unzip the new version into
a new folder, move the `data` and `backups` folders across into it, run `./deploy/macos/install.sh`
there, then `./deploy/macos/start-at-login.sh --shared`.

## 9. Stopping

```
./deploy/macos/stop.sh
```

This stops the app and the evening backup and stops them starting at login. The data stays in `data/`.

## If something goes wrong

- **The page doesn't open from other computers:** check the Mac is awake and logged in, that you used
  `--shared`, and that the macOS firewall allows Python (System Settings › Network › Firewall ›
  Options).
- **What happened?** The log is `~/Library/Logs/SawingPatterns/app.log`; backups log to `backup.log`
  next to it.
- **"Address already in use":** something else uses port 8000. Run
  `./deploy/macos/start-at-login.sh --shared --port 8010` and use the new address.
- **Installing fails at `access-parser`:** run `.venv/bin/python -m pip install --upgrade pip setuptools`
  and `./deploy/macos/install.sh` again.

## Good to know

- Run only **one** copy of the app against the database. A handful of people using it at once is fine.
- The app has **no logins**: anyone who can reach the address can see and change everything. Keep it on
  the office network; don't open it to the internet.
