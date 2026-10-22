# Analysis

Two places:

- the **dashboard**, which shows the main numbers live
- `analysis/make_figures.py`, which produces the report figures and the statistics

Both read the same database.

```powershell
# reads hti_study.db in the project folder
.venv\Scripts\python analysis\make_figures.py --study pilot
.venv\Scripts\python analysis\make_figures.py --study main
```

Figures go to `analysis/figures/`, with statistics in `stats_pilot.txt` and `stats_main.txt`.

## Pilot (choosing the threshold)

1. Per-person baseline from the 2 warm-ups: median and 1.4826 × MAD per sign.
2. Minimum spreads = the median pilot spread, never below the design minimum.
3. Score timeline for every pilot round, using the same code as live.
4. For each threshold from 1.0 to 3.0, simulate the live trigger rules and compare the pop-ups with the replay labels
   (match margin 3 s), giving:
   - precision = hits ÷ pop-ups
   - recall = labelled moments caught ÷ labelled moments
   - false alarms per round
5. **Pre-registered rule:** the highest recall with precision ≥ 70% and ≤ 1 false alarm per round; ties go to the
   higher threshold.
6. **Leave-one-person-out:** choose the threshold on all but one person, test it on that person, and repeat for
   everyone.
7. The comparison detectors (maximum z, B only, I only) are only reported.
8. Checks:
   - chance level (share of time marked unsure)
   - phone-set difficulty
   - label durations vs detection delay
   - label lag
   - speed histogram
   - share of people below the minimum spread

## Main study

| Claim | Measure | Test |
| --- | --- | --- |
| 1. The detector catches real hesitation | "Were you unsure just now?" yes rate, C3 vs C4; AUC of each detector at the random C4 moments | Two proportions with Wilson CIs; AUC (Mann–Whitney) |
| 2. Faster | decision time | Linear mixed model on log(time) with condition and set as fixed effects, position as a covariate, and a random intercept per participant; report the time ratio exp(β) |
| 3. Not worse (ideally better) | **rank of the chosen phone (main)**, % correct, switch rate, dominated choices | Linear mixed model on rank; GEE logistic on correct; report estimates with 95% CIs (no strict non-inferiority claim: one task per condition is too little data) |
| 4. Timing matters | C3 vs C4 on all of the above, plus acceptance and intrusiveness | Same models (C3 vs C4 contrast) |
| 5. Not annoying | NASA-TLX, intrusiveness | Means with CIs; Friedman / Wilcoxon for ratings |
| 6. Help solves the hesitation | score 10 s before vs after accepted vs dismissed pop-ups; event-aligned curve | Paired comparison |

- Apply the **Holm correction** across the family of condition contrasts you report.
- Report effect sizes and confidence intervals, not only p-values.
- Report all pre-stated outcomes, including the ones that did not work out.

## Figure list (protocol numbers)

| # | File | Shows |
| --- | --- | --- |
| 1 | 01_trajectories.png | a calm vs a hesitant round |
| 2 | 02_heatmap.png | where cursors spend time |
| 3 | 03_timeline.png | one round: score, z-scores, marked unsure moments, pop-ups |
| 4 | 04_precision_recall.png | threshold sweep with the 70% rule and chance level |
| 5 | 05_leave_one_out.png | detector on unseen people |
| 7 | 07_set_difficulty.png | phone sets equally hard |
| 8 | 08_unsure_yes_rate.png | Smart vs Random: "were you unsure?" |
| 9 | 09_decision_time.png | decision time per condition |
| 10–11 | 10_11_quality.png | correctness with CIs; switch and dominated rates |
| 12 | 12_speed_vs_quality.png | speed against rank |
| 13 | 13_paired_time.png | each person, No AI vs Smart |
| 14 | 14_score_around_popup.png | event-aligned score |
| 15 | 15_popup_choices.png | what people did with pop-ups |
| 16 | 16_final_move_curvature.png | maximum deviation of the final move to Buy |
| 17–18 | 17_18_questionnaires.png | workload, feelings, ratings of help |
| 19–20 | 19_20_sus_preference.png | SUS, preference ranking |
| 21 | 21_order_check.png | counterbalancing check |
| 22 | 22_roc_random_moments.png | ROC of the 4 detectors at random moments |

Plot 6 (which signs contribute most) can be read off the z-scores of hits vs misses in the tick files.
