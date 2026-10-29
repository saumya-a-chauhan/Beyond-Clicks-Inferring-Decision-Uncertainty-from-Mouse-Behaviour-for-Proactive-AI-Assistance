# Data dictionary

## Results sheet (dashboard → Data & Excel)

The Excel download has a **Pilot** and a **Main** sheet with the same columns, one row per participant and shopping
round, and an **About** sheet that explains every column (the list lives in `app/sheets.py`). Key columns:
`site` (laptop that recorded the data), `participant`, `age`, `gender` (from the "About you" step), `round`, `condition`, `decision_time_s`, `correct`, `rank`,
`switched`, pop-up counts, confidence, NASA-TLX, SAM, help ratings, trust, SUS, preference rank, and the round's mouse
summary (`app/mouse.py`): `mouse_points`, `mouse_path_px`, `mouse_moving_s`, `mouse_resting_s`, `mouse_speed_px_s`,
`clicks`, `details_opened`, `card_switches` (sign B over the round), `longest_spec_rest_s` (F), `longest_empty_rest_s`
(I), `scroll_events`, `scroll_flips` (S), `hover_by_phone`, `all_seen_s`, `score_peak`, `score_mean`, `threshold_used`,
`time_over_threshold_s`.

With **Include all mouse-movement data** ticked, three more sheets are added:

- **Mouse signs**: one row per detector check (every 0.5 s) in each shopping round: `raw_B..raw_S` (the 5 signs over the
  last 3 s), `z_B..z_S` (z-scores against the warm-up baseline), `score` (mean of the 5 z-scores), `over_threshold`,
  `all_seen`.
- **Mouse raw**: every logged event of every task, warm-ups included: `t_ms`, `type` (move / scroll / click), `x`, `y`,
  `scroll_y`, `zone`, `clicked`. Continues on "Mouse raw 2", ... after 1,000,000 rows (Excel's limit is 1,048,576).
- **Unsure marks**: the pilot replay marks, `start_s`, `end_s`, `length_s`.

The Excel file is for reading results. Only the study-data CSV below can be uploaded: the Excel is a summary built from
the data and cannot rebuild it.

## Study-data CSV (dashboard → Data & Excel → Download CSV / Upload CSV)

The complete database in one file (`app/datacsv.py`): columns `table`, `key`, `part`, `parts`, `data`. Each line is one
database row (participants, tasks, event_batches, popups, ai_requests, labels, responses, settings, audit) as JSON;
dates are `{"$dt": iso}`, binary data (gzipped mouse events, detector ticks) is `{"$b64": base64}`. Rows longer than
30,000 characters are split over several lines (`part` of `parts`). The `_meta` line holds the format version, the
source laptop and the number of rows per table; a file whose counts do not match (cut off or edited) is refused before
anything changes. Session tokens are never exported; the laptop name (`site_name` setting) stays with each laptop.
Loading a file **overrides** all study data on the receiving laptop: the database then holds exactly the file's data
(a backup is made first), so every page and analysis uses only it, and the dashboard says "Data overridden".

## Raw data ZIP

The ZIP export (dashboard → Backups & tools) contains these files. Times are milliseconds since the task started
unless stated otherwise.

## participants.csv

| Column | Meaning |
| --- | --- |
| code | P01… (pilot) or M01… (main). The only identifier. |
| study | pilot or main |
| slot | assignment slot number (order of arrival) |
| condition_order | main: e.g. ["C2","C3","C1","C4"]: condition of rounds 1–4 |
| set_order | phone set of rounds 1–4, e.g. ["S3","S4","S1","S2"] |
| pilot_ai_check | true if this pilot person got the extra AI round |
| plan | JSON list of the screens shown |
| step_index | last screen reached |
| status | started, completed, declined |
| device | JSON: viewport and screen size, devicePixelRatio, pointer types seen, mouse/zoom confirmations |
| baseline | JSON: per sign (B, F, I, W, S) the median, spread and number of checks from the 2 warm-ups |
| settings_snapshot | detector settings in force when this person started |
| excluded, notes | researcher exclusion and its reason |
| simulated | true for fake participants from scripts/simulate.py |

## tasks.csv (one row per warm-up, practice or round)

| Column | Meaning |
| --- | --- |
| task_key | baseline1, baseline2, practice, t1–t4, ai |
| kind | baseline, practice, main, pilot_ai |
| position | round number 1–4 |
| condition | C1 No AI, C2 Ask AI, C3 Smart pop-up, C4 Random pop-up (pilot rounds = C1; practice = DEMO) |
| set_id | phone set |
| card_order | phone ids from left to right (shuffled per task) |
| viewport | window size at task start |
| decision_ms | time from task start to confirming the purchase |
| chosen, correct, rank | first choice, whether it was the correct phone, its rank (1 correct, 2 main trap, 3 second trap, 4 dominated) |
| final_choice, final_correct, final_rank, switched | after the side-by-side switch test |

## events/<code>_<task>.csv (raw cursor log)

| Column | Meaning |
| --- | --- |
| t_ms | time |
| type | move, scroll, click |
| x, y | cursor position in the window (clientX/Y), px |
| scroll_y | page scroll position (scroll rows) |
| zone | what is under the cursor: card:<id>, spec:<id>:<spec>, read:card, read:details, ui:*, empty |
| label | for clicks: e.g. details:S1A, buy:S1B, ask_open |

## ticks/<code>_<task>.csv (detector output every 0.5 s, recomputed after the task)

`seen` (all phones seen), `raw_B…raw_S` (sign values), `z_B…z_S` (z-scores), `score_avg` (main detector),
`score_max`, `score_B`, `score_I` (comparison detectors).

## popups.csv

| Column | Meaning |
| --- | --- |
| t_ms | when the pop-up appeared |
| source | detector (C3) or random (C4) |
| predicted_type | compare, explain or general (from the biggest sign) |
| pair, spec | phones and spec the offer refers to |
| score, zs | detector score and z-scores at that moment |
| unsure_answer, unsure_ms | answer to "were you unsure just now?" |
| choice, choice_ms | compare, explain, general or dismiss |
| closed_ms | when the answer panel was closed |

## ai_requests.csv

Every AI answer shown:
- `origin`: popup or ask
- `mode`: compare, explain, general or ask
- `args`
- `provider`: gemini, groq, fallback, or cache:<provider>
- `model`
- `response`: the exact text shown
- `latency_ms`
- `error`

## labels.csv (pilot replay)

`intervals`: JSON list of [start_ms, end_ms] when the person held SPACE ("I remember feeling unsure").

## responses.csv

One row per completed screen. `kind` says which screen, and `data` holds the answers as JSON:

- **consent:** agree
- **device_check:** device info
- **switch:** final_choice, switched
- **confidence:** confidence 1–7
- **post_task:**
  - confidence 1–7
  - TLX: mental, physical, temporal, performance, effort, frustration (0–100, raw NASA-TLX)
  - valence and arousal 1–9
  - for AI rounds: helpful, timing, intrusive and trust1–4 (1–7)
- **sus:** q1–q10 (1–5, standard SUS; the score is computed in the analysis)
- **ranking:** ranks per condition (1 = best)
- **interview:** free text q1–q3
- **debrief:** keep

## settings.json and audit.csv

The current settings (detector, frozen state, assignment slots, pilot analysis summary) and a log of researcher
actions (freeze, unfreeze, exclusions, deletions, detector edits).

## About-you answers (responses.csv, kind = demographics)

`age` (whole number, 18 to 100), `gender` (`woman`, `man`, `non-binary`, `self-describe`, `prefer-not`) and
`gender_self` (the participant's own words when they chose self-describe). Collected right after consent; no name is
ever asked. The server refuses missing or invalid answers.

