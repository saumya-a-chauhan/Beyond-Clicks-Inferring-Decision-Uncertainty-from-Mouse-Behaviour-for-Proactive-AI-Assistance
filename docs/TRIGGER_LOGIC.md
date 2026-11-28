# When the AI pop-up appears: final logic (settings revision 4)

All numbers below come from the 6 pilot participants (P01–P06, 24 rounds without AI, 40 self-marked "unsure"
moments). A pop-up counts as **right** if it lands within 3 s of a moment the participant marked as unsure in the
replay. **Chance level is 30%**: people marked themselves unsure 30% of the time, so a pop-up at a random moment is
right about 30% of the time.

## The rule in one picture

```
round starts ──► looks at all 4 phones (each ≥ 1 s) ──► ...
                     │
     SMART (C3)      ├─ hesitation score ≥ 1.75 at a check ───────────────► pop-up   (stage "main")
                     └─ none after 10 s: first check with score ≥ 1.0 ────► pop-up   (stage "extra")
     RANDOM (C4)     └─ at a delay drawn from Smart's own pilot delays ───► pop-up   (stage "yoked")
     BOTH            Buy clicked and still no pop-up ──────────────────────► pop-up first (stage "at_buy")
```

Several pop-ups per round: whenever the score reaches 1.75 again, Smart pops up again; Random's later pop-ups come
at random at Smart's pilot rate (0.43 per minute). Nothing fires while a pop-up is open; the next one can come
**10 s after the previous one was closed** (20 s after "No thanks"; if the person asked for help and left the answer
open, after ~25 s of reading), **up to 5 per round**.

## Every value and why

| Value | Final | Why (evidence) |
| --- | --- | --- |
| Check interval | 0.5 s | Feels immediate (< 1 s response, Nielsen 1993). |
| Window | 3 s | Holds one full A → B → A comparison between two phones. Shorter windows (1.5 s, 2 s) were tested on the pilot and were not better. |
| Hesitation score | mean of 5 z-scores | 5 signs (back-and-forth, freezing on a spec, idle pause, wandering, scroll reversals), each compared with the person's own warm-up. Equal weights: 6 people cannot train weights (Dawes 1979). Single-sign detectors never reached 70% right at any threshold; the average did. |
| **Threshold** | **1.75** | Chosen by the rule written before the pilot: highest share of unsure moments caught, among thresholds with ≥ 70% of pop-ups right and ≤ 1 wrong pop-up per round. 1.75: 4 of 5 right (80%), 83% on held-out people. **1.5 fails the rule**: 44% right, close to chance. |
| **Detection time** | **3.5 s** (one check, was 5 s) | The pilot's unsure moments lasted a median **2.2 s**. Waiting for 4 checks in a row (5 s) missed most of them. With one check the rule still passes (80%). It is also the only setting that works on the serverless site: a count of checks in a row is lost between requests. |
| "All phones seen" | each card ≥ 1 s | No pop-up before the person has looked at every phone: there is nothing to be unsure about yet. Pilot: reached after a median **28.5 s**. 1 s is the value the pilot was run with; 0.35 s only moved this 1 s earlier. |
| **Second chance (Smart)** | **10 s after all seen, score ≥ 1.0** | With the threshold alone only 5 of 24 pilot rounds would have a pop-up. With this, 13 of 24, and **69% right vs 41%** for Random with the same timing. Waiting only 5 s gave more rounds (16) but Smart was then barely better than timing (56% vs 45%). 12 combinations were compared (wait 5 / 8 / 10 s × bar 0.5 / 0.75 / 1.0 × threshold 1.5 / 1.75). |
| **Random timing** | yoked to Smart | Random's first pop-up comes at a delay after "all seen" drawn from Smart's own 13 pilot delays (0.5–17 s, mostly 10 s). So both conditions pop up equally often and at the same points in a round; **the only difference is whether the person's hesitation decided the moment**. That is what makes C3 vs C4 a fair test. |
| **At Buy** | both conditions | If Buy is clicked before any pop-up, the pop-up comes first, the same in both conditions, so every AI round shows the assistant. These pop-ups are reported separately and left out of the Smart vs Random comparison, because they are identical by design. |
| **Gap between pop-ups** | **10 s after the previous one was closed** (20 s after "No thanks") | Counted from closing, so reading the answer is not cut short (an open answer counts as ~25 s of reading: ~100 words at 240 words/min, Brysbaert 2019). The old 45 s counted from the pop-up itself, and rounds last ~50 s, so a second pop-up never happened. Pilot with a 10 s gap: 16 pop-ups instead of 13, **75% right**, and **all 3 later pop-ups landed on real unsure moments**. Doubling after "No thanks" respects "not now" (Amershi et al. 2019). |
| **Max pop-ups** | **5 per round** | Upper safety limit against interrupting too often (Bailey & Konstan 2006); the pilot never needed more than 4. |
| Random's later pop-ups | 0.43 per minute | Smart's pilot rate of second and later pop-ups, so both conditions pop up equally often. |

## What was wrong before (revision 2) and why it changed

Revision 2 added timers that forced a pop-up **9 s (Random) and 14 s (Smart) after the round started**, in the
browser, plus a server timer at 10 s. Pilot participants had not even looked at all phones by then (median 28.5 s),
so almost every pop-up in both conditions came from a timer: Smart and Random became the same thing. Timer pop-ups
were stored with a made-up hesitation score of 1.5, and the short survey copied one trust answer into four fields.
Revision 3 removes all timers, stores only real scores and real answers, and applies once to the frozen settings
(logged in the audit log). **Main-study data collected under revision 2 cannot be used for the Smart vs Random
comparison**; clear it (Backups & tools → Clear main-study data) and restart the main study at M01.

## Honest limits to report

- All values were checked on the same 6 people they were chosen on; new people may do somewhat worse.
- The pilot's 80% rests on 5 pop-ups (plausible range about 38–96%).
- Rounds where Buy comes before any timed pop-up get the at-Buy pop-up; how many there are is itself a result.
