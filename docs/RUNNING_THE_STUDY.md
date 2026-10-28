# Running the study: step-by-step guide for the team

This is the detailed protocol. The step-by-step guide for whoever runs sessions is inside the site at http://localhost:8000/guide (file `static/guide.html`). Read that one first.

## 0. One-time setup (before any participant)

1. On the study laptop, double-click `start_study.bat` (see the README). The **study URL** is
   http://localhost:8000 and the **researcher password** is `ADMIN_PASSWORD` in `.env`.
2. Log in at http://localhost:8000/admin.
3. **Settings tab → Consent page information:** fill in team names, contact emails, supervisor, the ethics approval
   number (or "pending"), and the reward. Save. This text appears on every participant's consent page.
4. **Backups & tools → Check the AI providers:** both Gemini and Groq should say `ok: true`.
5. Make sure no simulated participants are left (**Backups & tools → Delete simulated participants**).
6. Bring an **external mouse**. Every session should use a mouse, browser zoom at 100%, and a full-screen window
   (F11). The device check screen asks participants to confirm this.

## 1. Pilot sessions (8–12 people, about 70 minutes each)

Before each session:

- Open the study URL on the laptop, full screen, zoom 100%, mouse plugged in.
- For the **last 3 pilot people only**: Settings → **Pilot AI check** → tick "Give new pilot participants the extra AI
  round" → Save. Untick it again after the third one.

During the session:

1. Click **Start pilot study** and hand the laptop to the participant.
2. They go through the steps themselves:
   1. consent and setup check
   2. 2 warm-ups
   3. 4 rounds without AI
   4. the **replay** of each round (holding SPACE while they remember feeling unsure)
   5. 3 interview questions
   6. the extra AI round, if switched on
3. Stay nearby but do not help with the phone choice. You may explain the SPACE-bar task if asked.
4. If the browser closes by accident, open the study URL again on the same laptop and click **Continue**.

After the session: in **Participants**, check that the person is `completed` and has 4 labels.

## 2. After the pilot: analyse and freeze

1. **Pilot analysis & freeze → Run pilot analysis.** Leave "include simulated" unticked.
2. Read the results:
   - **Threshold picked by the rule.** The rule was written down in advance: highest recall among thresholds with
     precision ≥ 70% and ≤ 1 false alarm per task; if two are almost equal, the higher one wins.
   - **Leave-one-out precision and recall.** This is how well the threshold works on people it has never seen.
   - **Chance level.** Our precision must be clearly above it.
   - **Phone sets.** Each should be 40–60% correct without AI. If a set is outside that range, change it in
     `app/data/phone_sets.json`, then re-check it with 2–3 extra pilot people.
   - **Timing checks:**
     - the median "unsure" moment should be longer than the detection time of about 5 s
     - unsure moments per task should fit within the maximum of 3 pop-ups
     - the label lag should fit within the 3 s match margin
   - **Speed histogram.** The dip between still and moving should be near 50 px/s.
   - **Minimum spreads.** A sign used for more than 30% of people is flagged "less reliable": report it.
3. If no threshold passes the rule: make one stated change (drop the weakest sign, or relax precision to 60%), write
   it down, and report it.
4. **Freeze.** Click **Freeze settings and open the main study**. If you type a different threshold from the rule's,
   you must write a note. Freezing saves:
   - the threshold
   - the minimum spreads
   - the random pop-up rate for the Random condition
   - the date

   It then locks them and unlocks the **Main study** button.
5. Take a screenshot of the pilot results for the midterm slides. Also run
   `analysis/make_figures.py --study pilot` for the report figures (plots 1–7).

Unfreezing exists only for serious problems. It needs a written reason, and that reason stays in the audit log forever.

## 3. Main sessions (24 people, about 75 minutes each)

1. Open the study URL, then click **Start main study**. The site assigns the participant's order automatically:
   - **Condition order:** balanced Latin square (Williams design) in random blocks of 4. Every 4 participants cover
     all 4 orders, so each condition appears equally often in each position.
   - **Phone sets:** rotated so that each condition is paired with each set once per block.
2. The participant goes through these steps:
   1. consent and setup check
   2. 2 warm-ups and a practice round, which shows an example pop-up and the Ask AI button
   3. 4 rounds. Before each round, one screen says what kind of help there is. Smart and Random look identical to
      the participant.
   4. After each round: the switch test, then a questionnaire (confidence, NASA-TLX, SAM, and for AI rounds: help
      ratings and trust)
   5. SUS for each AI round, a ranking of the rounds, 3 questions
   6. **debrief**, which explains the random pop-ups and offers data deletion
3. Do not tell participants that one round is random before the debrief.
4. Aim for 24 completed participants. Because assignment is in blocks of 4, the design is balanced at 4, 8, 12, … 24.
   If someone stops early, the next participant gets the next slot. That's fine: report any incomplete participants.

## 4. After the main study

1. **Main study results → Compute results**:
   - the "unsure just now?" yes rate for Smart vs Random
   - AUC at random moments
   - speed, rank, correctness
   - questionnaires
   - the order check
2. **Backups & tools → Download ZIP** for an archive of everything.
3. On the study laptop, run `.venv\Scripts\python analysis\make_figures.py --study main` (plots 8–22 and the
   mixed-model statistics). Figures are saved in `analysis/figures/`.
4. If someone asks for their data to be deleted later: in **Participants**, delete that participant by code.

## Exclusions (decide before looking at results)

Exclude a participant (Participants → Exclude, with a reason) only for these pre-stated reasons:

- they used a touchpad
- they did not finish the 4 rounds
- there was a technical failure, for example the logging stopped
- they clearly did not try (chose within 5 seconds in every round)

Excluded participants stay in the export but are left out of analyses.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The page does not open | The website is not running. Double-click `start_study.bat` and keep its window open. |
| AI answers say "not available right now" | Both LLM providers failed; written fallback answers are shown. Check the keys in `.env` (restart `start_study.bat` after editing it), and run the AI provider check. |
| "Session not found" | The browser data was cleared. Start a new session; delete or exclude the broken one. |
| Window too small | Use full screen (F11). The setup check needs at least 1200 px width. |
| Main study button is locked | Settings are not frozen yet (step 2). |
