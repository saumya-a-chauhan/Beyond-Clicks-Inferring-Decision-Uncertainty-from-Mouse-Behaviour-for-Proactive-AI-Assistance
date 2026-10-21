# How hesitation is detected

Every 0.5 s the system looks at the last 3 s of mouse movement. It measures 5 "stuck" signs, compares each with this
person's own normal (their baseline), averages them into one score, and shows a pop-up only if the score stays above
the threshold for 2 s.

Code: `app/features.py` (signs, z-scores) and `app/detector.py` (trigger rules). The same code runs live
(`app/live.py`) and in the pilot analysis (`app/analysis.py`).

## Step 0: what is recorded

- Cursor position and time about 60 times per second (`[t, x, y, zone]`), scroll position (`[t, scrollY, zone]`)
  and clicks.
- **Zones** come from the page itself:
  - `card:<phone>`: a phone card
  - `spec:<phone>:<spec>`: one spec row inside a card
  - `read:card` and `read:details`: the requirement card and the details/review panel. Resting there is reading,
    not hesitation.
  - `ui:*`: the AI panel and buttons
  - `empty`: everything else

## Step 1: this person's normal

Two easy warm-up tasks in the same layout:

1. "Find the phone that comes in Blue": normal scanning and clicking.
2. "Find the phone with a 4 nm processor": normal reading of a technical spec row, with no conflict.

For each sign we store the **median** and the **spread = 1.4826 × MAD** (median absolute deviation) over all 0.5 s
checks of both tasks.

## Step 2: explore first

No pop-up until every phone card has been hovered for at least 1 s in total. Looking at everything the first time is
browsing, not hesitation.

## Step 3: the 5 signs (window = last 3 s)

| Sign | Meaning | How it is counted |
| --- | --- | --- |
| **B** Back-and-forth | torn between phones | switches from one card to a different card. A visit counts only if it lasts ≥ 200 ms; non-card zones in between are ignored |
| **F** Freezing | stuck on a spec | longest continuous rest (speed < 50 px/s) on the same spec row, in seconds (max 3) |
| **I** Pausing | stopped to think | longest continuous rest in empty space (not a spec row, not a reading zone), in seconds (max 3) |
| **W** Wandering | unsure where to go | path length ÷ straight distance for moves between rest points (rest point = < 50 px/s for ≥ 150 ms). Only moves of ≥ 30 px straight distance count; with no such move, W is "no data" and its z is 0 |
| **S** Scroll flip-flop | re-checking | scroll direction reversals |

A segment that is still open at time t (the cursor hasn't moved since the last sample) counts as resting, so the live
system and the offline analysis compute exactly the same values.

## Step 4: the z-score

```
z = (value now − typical value) ÷ max(typical spread, minimum spread)
```

- Negative z is set to 0: less than usual is not "negative hesitation".
- z is capped at 5, so one extreme sign cannot decide alone.
- **Minimum spread:** the median pilot spread for that sign, but never below the provisional design minimum.
  Counting signs (B, S) are often 0 in a short baseline, so the minimum is used often. The pilot analysis reports for
  how many people.

## Step 5: the score

```
Score = (zB + zF + zI + zW + zS) ÷ 5
```

Equal weights, because a small pilot cannot learn weights without overfitting (Dawes, 1979). Three comparison
detectors are reported alongside but never chosen from the pilot: the **maximum** z, **B alone** and **I alone**. They
are compared fairly at random moments in the main study (see below).

## Step 6: trigger rule (all must be true)

1. All 4 phones seen (step 2).
2. Score ≥ threshold (provisional 1.5; final value from the pilot).
3. True for 4 checks in a row (about 2 s; the windows overlap, so it is about 5 s of evidence).
4. ≥ 45 s since the last pop-up, or ≥ 90 s if the participant clicked "No thanks".
5. Fewer than 3 pop-ups so far in this round.

**Random condition (C4):** same rules 1, 4 and 5, but instead of the score, a pop-up fires at random. The chance per
check is set so that the average rate matches the Smart condition's rate in the pilot.

## Step 7: what the pop-up shows

1. Screen 1, identical in Smart and Random: **"Quick question: were you unsure just now?" Yes / No**. No phone names
   appear before the answer, so the question cannot lead them.
2. Screen 2 shows the help offer. Which option comes first depends on the biggest sign:
   - B biggest → **Compare** the two phones with the most hover time in the last 10 s
   - F biggest → **Explain** the spec row rested on the longest
   - otherwise → **Overview**

   All three options are always shown, so we can measure whether our guess was the one people clicked.

## Validation

- **Pilot:** pop-ups simulated on the replay labels give precision, recall and false alarms per task. A pop-up is a
  hit if it falls inside a marked "unsure" range or within 3 s of it.
- **Main study:**
  - The "were you unsure?" yes rate in Smart vs Random shows lift over chance.
  - At the random (C4) moments, the answers are an unbiased sample, so each detector's score at those moments gives
    an ROC curve and an AUC.

## Known limits

- The cursor is not the eye.
- Resting can mean reading or being stuck.
- The baseline is short (about 3 minutes).
- Different laptops, mice and screens change speeds. We log device information, and the per-person baseline is
  measured on the same device in the same session.
- The detector is only called valid if it beats chance on the participants' own answers.
