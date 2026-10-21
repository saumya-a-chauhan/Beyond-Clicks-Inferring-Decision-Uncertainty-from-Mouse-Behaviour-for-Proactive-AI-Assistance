# Beyond Clicks: Inferring Decision Uncertainty from Mouse Behaviour for Proactive AI Assistance

HTI (DS 4101) course project, Track 1 (experimentation).

A web-based experiment platform that watches **how people move the mouse while choosing a phone**, detects
**hesitation** in real time, and offers **AI help (an LLM) at that moment**. It compares four conditions,
**No AI, Ask AI (on demand), Smart pop-up (our detector) and Random pop-up (control)**, on decision **speed**
and decision **quality**, and checks whether the pop-up came when people were really unsure.

Everything runs in one website:

- **Participants** open the site on any laptop, click **Pilot study** or **Main study**, and are guided step by step.
  They never see any data.
- **Researchers** log in with a password at `/admin` to see participants, run the pilot analysis, **freeze** the
  settings (which unlocks the main study), view results and download all data.

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
- Offline analysis script with 22 figures and mixed-effects models; simulator for testing; unit tests.

## Quick start (local)

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-analysis.txt      # on Mac/Linux: .venv/bin/pip
cp .env.example .env                                         # then fill in the values
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000 (participants) and http://localhost:8000/admin (researchers).

To run the study from **any teammate's laptop**, deploy it once to the cloud: [docs/DEPLOY.md](docs/DEPLOY.md).

## Testing without real people

```bash
# fake pilot (10 people, last 3 with the AI check), analyse + freeze, then 24 fake main participants
.venv/Scripts/python scripts/simulate.py --pilot 10 --ai-check 3 --freeze --main 24
.venv/Scripts/python analysis/make_figures.py --study pilot --include-simulated
.venv/Scripts/python analysis/make_figures.py --study main --include-simulated
.venv/Scripts/python -m pytest -q tests
```

Use a separate test database for this (`DATABASE_URL=sqlite:///./test.db`), or delete simulated participants in the
dashboard (Export & tools) before the real study. Never freeze the real study on simulated data.

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
  data/phone_sets.json   the 6 phone sets (practice, 4 main, 1 pilot-AI)
static/           website (home, participant runner, researcher dashboard)
analysis/make_figures.py   report figures + statistics
scripts/simulate.py        fake participants for testing
tests/            unit tests
docs/             protocol, detector, values, data dictionary, deployment, project page
```

## Data and privacy

No names, camera or microphone. Participants get a code (P01, M01). Cursor data, choices and answers are stored in the
study database; only researchers with the password can see or export them. Participants can delete their own data at
the end. API keys and the password live in environment variables, never in the code. See
[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

## Team

HTI (DS 4101), Plaksha University. Add team member names here.
