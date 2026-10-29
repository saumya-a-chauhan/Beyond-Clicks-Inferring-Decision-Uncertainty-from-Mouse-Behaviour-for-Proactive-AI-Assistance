# Beyond Clicks: Inferring Decision Uncertainty from Mouse Behaviour for Proactive AI Assistance

HTI (DS 4101) course project, Track 1 (experimentation).

A web-based experiment platform that watches **how people move the mouse while choosing a phone**, detects
**hesitation** in real time, and offers **AI help (an LLM) at that moment**. It compares four conditions,
**No AI, Ask AI (on demand), Smart pop-up (our detector) and Random pop-up (control)**, on decision **speed**
and decision **quality**, and checks whether the pop-up came when people were really unsure.

Everything runs in one website, on **one study laptop** (data never leaves it):

- **Participants** sit at the laptop, click **Pilot study** or **Main study**, and are guided step by step.
  They never see any data.
- **Researchers** log in with a password at `/admin` to see participants, run the pilot analysis, **freeze** the
  settings (which unlocks the main study), view results and download all data.

### What does "freeze settings" do?

During the pilot **nothing is adjusted live**: no pop-ups appear and the threshold does not change while people take
part. The site only records mouse movement and the "I was unsure" replay labels.

When all pilot people are done, a researcher clicks **Run pilot analysis** in the dashboard. That is the moment the
threshold is **calculated**: the site replays every pilot task through the detector at thresholds 1.0 to 3.0,
compares the would-be pop-ups with the replay labels, and picks the threshold with the rule written down in advance
(highest recall with precision at least 70% and at most 1 false alarm per task).

**Freeze** then locks that threshold and every other detector number (with the date) and **unlocks the Main study
button**. From then on the main study uses exactly those numbers for every participant. You can re-run the pilot
analysis as often as you like before freezing; after freezing, changing anything needs "Unfreeze" with a written
reason, which stays in the audit log. This is pre-registration: it shows we did not tune the threshold after seeing
the main-study results.

## How the study works

| Phase | Who | What happens |
| --- | --- | --- |
| 1. Pilot | 8–12 people | 2 warm-up tasks (personal baseline), 4 shopping rounds **without AI**, then a **replay** of their own cursor where they hold SPACE while they remember feeling unsure. The last 3 also try one round with the AI pop-up. |
| 2. Analysis and freeze | researchers | The dashboard simulates the live detector on the pilot data, compares it with the replay labels, picks the threshold with a pre-registered rule, checks it with leave-one-person-out, and **freezes** all settings. The main study unlocks. |
| 3. Main study | 24 people | 2 warm-ups + practice, then 4 rounds, one per condition, in a **balanced Latin-square order** (random but balanced), with questionnaires after each round. |

Full protocol: [docs/RUNNING_THE_STUDY.md](docs/RUNNING_THE_STUDY.md). How hesitation is detected, with every number
explained: [docs/DETECTOR.md](docs/DETECTOR.md) and [docs/VALUES.md](docs/VALUES.md).

## Features

- Live cursor logging (~60 Hz), scroll and click logging, per task.
- **Hesitation detector** with 5 signs (back-and-forth, freezing on a spec, pausing, wandering, scroll flip-flops),
  per-person modified z-scores against a baseline, and trigger rules (persistence, cooldowns, max pop-ups).
  The **same Python code** runs live and in the analysis, so the frozen threshold means the same thing in both.
- Pop-up flow: neutral "were you unsure just now?" question first (identical in Smart and Random), then the help offer
  (Compare / Explain a spec / Overview).
- AI help from **Gemini**, falling back to **Groq**, then to written answers. Answers are grounded only in the phone data
  and cached, so every participant gets identical help for identical requests.
- Replay labelling built from the logged data (no screen recording needed).
- Researcher dashboard: participants, pilot threshold sweep with charts, leave-one-out, freeze/unfreeze (audited),
  main results (yes-rates, AUC at random moments, speed, quality, questionnaires), ZIP export.
- **Data & Excel tab:** download an Excel file with a **Pilot** and a **Main** sheet (one row per participant and round,
  always up to date, with each round's mouse summary; optionally every cursor point and the detector's 0.5 s checks);
  **Download CSV** saves the complete study data in one file, and **Upload CSV** loads such a file
  so every page, the pilot analysis, the freeze, the results and the figures run on that data.
- **Data safety:** every save goes straight into `hti_study.db`; automatic backups in `backups/` (at start, every 15
  minutes while data changes, after each participant, at freeze, before deletes and CSV loads); full backup download.
- **Experimenter guide** inside the site at `/guide`: setup, pilot, freeze, main study, data, troubleshooting.
- Offline analysis script with 22 figures and mixed-effects models; simulator for testing; unit tests.

## Quick start (on the study laptop)

You need **Python 3.11 or newer** ([python.org](https://www.python.org/downloads/), tick "Add Python to PATH").

**Windows, easiest:** double-click `start_study.bat`. The first time it creates the Python environment and installs
everything (a few minutes), then it starts the site and opens the browser. Keep its window open during sessions;
close it to stop the site.

**Or by hand** (PowerShell, inside the project folder):

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-analysis.txt
copy .env.example .env        # first time only, then open .env and fill in the password and API keys
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

- http://localhost:8000 for participants (Pilot study / Main study buttons)
- http://localhost:8000/admin for researchers (password = `ADMIN_PASSWORD` in `.env`)

All data is saved in `hti_study.db` in this folder. Back it up (copy the file) after every session day, and
download a ZIP from the dashboard (**Backups & tools**) for analysis.

## Where the data is, and sharing it

- All data is in **one file, `hti_study.db`**, in the project folder. Every save is written into it immediately, so it
  survives closing the window, a crash or a restart, and a copy of that one file contains everything.
- Automatic complete copies go to the **`backups/`** folder (newest 40 kept). Restoring one is described in the guide.
- **Zipping the folder:** the data travels only if `hti_study.db` is inside the ZIP. Never include `.venv` (about
  500 MB, works only on the PC that made it; the start script recreates it).
- **Moving the data to another laptop:** on the experiment laptop, dashboard → **Data & Excel** → **Download CSV**.
  On the analysis laptop, **Upload CSV**: that laptop then shows exactly the same participants, pilot analysis, freeze,
  results and Excel, and `analysis/make_figures.py` runs on it. A backup is made before loading. Run the **whole study
  on one laptop** and never upload a CSV on the experiment laptop itself.

To make a clean code-only ZIP without data or secrets: `git archive -o Beyond-Clicks-code.zip HEAD` (teammates then
copy `.env.example` to `.env` and fill it in).

A cloud version (Render + Neon) is possible later; see [docs/DEPLOY.md](docs/DEPLOY.md). It is not needed for a
single study laptop.

## Testing without real people

Always use a **separate test database**, so fake people never mix with real ones (PowerShell):

```powershell
$env:DATABASE_URL = "sqlite:///./test.db"; $env:LLM_DISABLED = "1"
# 10 fake pilot people (last 3 with the AI check), analyse + freeze, then 24 fake main-study people
.venv\Scripts\python scripts\simulate.py --pilot 10 --ai-check 3 --freeze --main 24
.venv\Scripts\python analysis\make_figures.py --study pilot --include-simulated
.venv\Scripts\python analysis\make_figures.py --study main --include-simulated
# look at the test site and dashboard with the fake data
.venv\Scripts\python -m uvicorn app.main:app --port 8001
# when finished: close PowerShell (clears the variables) and delete test.db
```

`.venv\Scripts\python -m pytest -q tests` runs the unit tests. Never freeze the real study on simulated data.

## Project structure

```
app/
  main.py         web server: participant API, researcher API, pages
  features.py     the 5 cursor signs, baseline, z-scores, detector scores
  detector.py     trigger rules (shared by live use and offline simulation)
  live.py         live detector state per running task
  analysis.py     pilot threshold selection, leave-one-out, main results
  llm.py          Gemini -> Groq -> fallback, grounded prompts, cache
  assign.py       balanced Latin square with permuted blocks
  plans.py        the screens each participant goes through
  phones.py       phone sets and scoring of choices
  db.py           database tables (SQLite locally, Postgres in the cloud)
  sheets.py       results sheet (Excel download)
  datacsv.py      study data as one CSV: download and load
  backup.py       automatic and manual database backups
  data/phone_sets.json   the 6 phone sets (practice, 4 main, 1 pilot-AI)
static/           website (home, participant runner, researcher dashboard, guide.html)
START_HERE.txt    first steps for a new laptop
start_study.bat / start_study.command   one-click start (Windows / Mac)
analysis/make_figures.py   report figures + statistics
scripts/simulate.py        fake participants for testing
tests/            unit tests
docs/             protocol, detector, values, data dictionary, deployment, project page
```

## Data and privacy

No names, camera or microphone; only age and gender are asked. Participants get a code (P01, M01). Cursor data, choices and answers are stored in the
study database; only researchers with the password can see or export them. Participants can delete their own data at
the end. API keys and the password live in environment variables, never in the code. See
[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

## Team

HTI (DS 4101), Plaksha University. Add team member names here.
