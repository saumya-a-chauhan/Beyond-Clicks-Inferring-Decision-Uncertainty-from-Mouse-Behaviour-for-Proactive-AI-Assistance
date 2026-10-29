# Every value and why

Each number has one kind of reason:
- **Paper:** from research
- **Pilot:** measured in our pilot
- **Design:** our stated choice, tested with a sensitivity analysis

Defaults live in `app/defaults.py`. The pilot replaces the threshold, the minimum spreads and the random pop-up rate,
and then they are frozen.

## Detector

| Value | Default | Why | Kind |
| --- | --- | --- | --- |
| Sampling | ~60 Hz (one sample per ≥ 16 ms) | What browsers give (about once per screen refresh); voluntary hand movement is mostly below ~10 Hz | Paper + technical |
| Check interval | 0.5 s | Responses under ~1 s feel immediate (Nielsen, 1993) | Paper |
| Window | 3 s | Holds at least one full A → B → A comparison; detection (~5 s) must be shorter than a typical unsure moment (checked in the pilot) | Pilot + Design |
| Lookback | 10 s | Extra history so a visit or rest that began before the window is measured correctly | Design |
| Visit minimum | 200 ms | Shorter than a typical eye fixation (~200–300 ms; Rayner, 1998): a quick pass is not "looking" | Paper |
| Resting speed | < 50 px/s | At 50 px/s the cursor moves < 8 px in 150 ms (less than a letter); confirmed by the dip in the pilot speed histogram | Pilot + Design |
| Rest point | ≥ 150 ms resting | Ignores brief slow-downs inside a movement; shorter than a fixation, so real pauses are caught | Design |
| Minimum move for W | 30 px | Hand jitter inflates path ÷ straight distance; near-zero distance makes the ratio blow up | Design (sensitivity 15 / 60 px) |
| Seen all phones | each card ≥ 1 s | Choice has stages: orientation, then evaluation, then verification (Russo & Leclerc, 1994); 1 s ≈ 3–4 fixations | Paper |
| Two baseline tasks | blue phone; 4 nm chip | Normal movement plus normal technical-spec reading, so reading is not mistaken for freezing | Design |
| Reading zones | requirement card, details panel | Resting there is reading, so it counts toward neither F nor I | Design (logic) |
| z formula | modified z (median, 1.4826 × MAD) | Signs have different units, so they must be put on one unitless scale before adding (the "mathiness" lecture). Each person is compared with themselves (no "average human"). Median-based statistics resist skew (Iglewicz & Hoaglin, 1993) | Paper |
| Minimum spread | max(median pilot spread, design minimum B 0.5, F 0.3 s, I 0.3 s, W 0.15, S 0.5) | Avoids dividing by almost zero (count signs are mostly 0 in baselines); the design minimum stops a near-zero pilot median from making a sign explode. Usage is logged, and flagged if > 30% of people need it | Pilot + Design |
| Negative z → 0 | | Hesitation means "more than usual"; a calm sign must not cancel a hesitant one | Design (logic) |
| z cap | 5 | One extreme sign should not decide alone | Design (sensitivity 3 / 10) |
| Equal weights | 1/5 each | Small pilot; equal weights predict about as well as fitted ones in small samples (Dawes, 1979) | Paper |
| Threshold | 1.5 provisional | Final value from the pilot rule | Pilot |
| Persistence | 4 checks (~2 s) | Removes one-off spikes | Pilot + Design |

## Pop-ups

| Value | Default | Why | Kind |
| --- | --- | --- | --- |
| Cooldown | 45 s | Longer than reading and using an answer: ~100 words at ~240 words/min (Brysbaert, 2019) ≈ 25 s, plus 15–20 s to act; checked against reading time in the pilot AI check | Paper + Pilot |
| After "No thanks" | 90 s | Dismissal means "not now"; human-AI guidelines say to support easy dismissal and learn from it (Amershi et al., 2019). Doubling is a simple back-off | Paper + Design |
| Max per round | 3 | Interruptions cost attention (Bailey & Konstan, 2006); just above the typical number of unsure moments per round in the pilot | Paper + Pilot |
| Neutral question first | "were you unsure just now?" | Content-free and identical in Smart and Random, so the answer is not led by the pop-up naming the phones | Design |
| Random pop-up rate | pilot rate per minute | Matches how often the Smart pop-up fires, so the two conditions differ only in timing | Pilot |

## Threshold selection

| Value | Default | Why | Kind |
| --- | --- | --- | --- |
| Threshold grid | 1.0 to 3.0 in steps of 0.25 | Covers sensitive to strict | Design |
| Match margin | 3 s | People press SPACE a little late in the replay; checked with the label-lag plot | Pilot |
| Precision | ≥ 70% | Wrong interruptions are costly (Horvitz, 1999), so it must be right most of the time; well above chance | Design |
| False alarms | ≤ 1 per round | At most one annoying pop-up per round | Design |
| Tie rule | recall within 2 points → higher threshold | Fewer interruptions when performance is equal | Design |

## Study

| Value | Default | Why | Kind |
| --- | --- | --- | --- |
| Phones per set | 4 | Decision time grows with options (Hick's law); large sets overload (Iyengar & Lepper, 2000). Fits on one screen; gives 1 correct, 2 traps, 1 dominated | Paper |
| Target accuracy without AI | 40–60% | Avoids ceiling and floor effects; variance p(1 − p) is largest at 50% | Paper (statistics) |
| Pilot size | 8–12 | Pilot rule of thumb is 12 (Julious, 2005); 8 is the minimum | Paper |
| Main size | 24 | Multiple of 4 for the balanced Latin square; detects d ≈ 0.6 at 80% power within-subjects | Paper (statistics) |
| Main quality measure | rank of chosen phone (1–4) | One yes/no per person per condition is too little data; rank carries more information | Design |
| Window before/after pop-up | 10 s | About two detection windows; does not reach the next pop-up (45 s cooldown) | Design |

## Sensitivity analysis (run offline after the study)

| Value | Values to test |
| --- | --- |
| Resting speed | 25 / 50 / 75 px/s |
| Window | 2 / 3 / 5 s |
| Persistence | 2 / 4 / 6 checks |
| z cap | 3 / 5 / 10 |
| Minimum move for W | 15 / 30 / 60 px |
| Pausing sign | with / without I |

The live cooldown can only be re-tested on detector precision and recall, not on decision outcomes.

To run one: copy the detector settings, change one value, and call `analysis.pilot_analysis()` or `compute_ticks()`
with that configuration.

**Please check every reference on Google Scholar before using it in slides.**

## Phone sets (app/data/phone_sets.json)

| Choice | Why |
| --- | --- |
| No summary scores (no "x / 100") | A single score turns the choice into a lookup. Real shoppers see spec-sheet terms and lab measurements, so hesitation comes from interpreting them. |
| Mixed units (minutes vs hours, GB vs TB vs MB, millions vs Indian lakhs, nits vs cd/m²) | Comparing needs conversion, as in real reviews; this is where "Explain a spec" and "Compare" help is genuinely useful. |
| "Bigger is not better" terms (lower lux, lower f-number, 1/1.4" sensor larger than 1/1.56", optical vs digital zoom) | Common real-world misreadings; the main trap exploits them. |
| Real trade-off: the correct phone wins Priority 1, the main trap wins Priority 2 and has flashier headline specs | No option dominates on everything the buyer wants, which is what creates genuine hesitation (choice under conflict). |
| One defensible correct answer, hidden true values per phone | Decision quality stays objective. `tests/test_phone_sets.py` checks every set: correct phone best on Priority 1 within budget, trap better on Priority 2, second trap over budget, dominated phone worse on everything. |
| Shopping screen: picture, colours, price and the start of the specs ("…"); **View details** opens all spec rows, which contain the measured values (screen-on time, low-light limit, zoom, brightness, free space, speed after 30 min) | Like a real shop page: people must open and compare details, which is the behaviour the detector reads. The measured values must be visible somewhere, or there would be no defensible correct answer; written inside long spec rows in mixed units, they are not obvious. `tests/test_phone_sets.py` checks every value is in the specs. |
| Lab-results table and short reviews only on the "change your choice?" screen after the round | The reviews state the answer in plain words, so showing them while shopping made the choice obvious. After the first choice they become the switch test: does seeing everything clearly side by side change the decision? |
| The AI sees only the specs, not the reviews | The AI must not know more than the participant, otherwise AI rounds would differ by information, not by timing. |
| Phone pictures (drawn, same style for every phone); 4 camera styles counterbalanced so each role gets each style once across S1–S4 | Looks attract people, as in a real shop, but no role (correct, trap, ...) is always the best-looking phone. |
| Pilot target 40–60% correct without AI | If a set is much easier or harder, change its numbers in the JSON and re-run the tests. |

