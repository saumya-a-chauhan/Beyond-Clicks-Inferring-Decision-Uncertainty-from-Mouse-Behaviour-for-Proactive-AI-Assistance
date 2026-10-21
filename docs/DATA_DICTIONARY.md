# Data dictionary

The ZIP export (dashboard → Export & tools) contains these files. Times are milliseconds since the task started
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
