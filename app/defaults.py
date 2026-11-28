"""Default (provisional) study settings. Every value is explained in docs/VALUES.md.

These are the values used BEFORE the pilot analysis. After the pilot, the researcher
dashboard computes the threshold (and minimum spreads, random pop-up rate) and
"freezes" them. Frozen settings cannot be changed from the dashboard.
"""

SIGNS = ["B", "F", "I", "W", "S"]

DETECTOR_DEFAULTS = {
    # timing
    "tick_ms": 500,            # check every 0.5 s (Nielsen 1993: < 1 s feels immediate)
    "window_ms": 3000,         # 3 s sliding window
    "lookback_ms": 10000,      # extra history used to know where a visit or rest began
    "persistence_ticks": 1,    # one check at/above threshold is enough: detection 3.5 s (pilot: unsure marks ~2 s long)
    # cursor event definitions
    "rest_speed_px_s": 50.0,   # resting = slower than 50 px/s
    "rest_point_ms": 150,      # a rest point = resting for >= 150 ms (segments moves for W)
    "visit_min_ms": 200,       # a card visit counts if >= 200 ms (Rayner 1998 fixation)
    "min_move_px": 30.0,       # wandering only counts moves with straight distance >= 30 px
    "seen_card_ms": 1000,      # "seen all phones" = each card hovered >= 1 s in total (the value the pilot used)
    # z-scores
    "z_cap": 5.0,
    "min_spread": {"B": 0.5, "F": 0.3, "I": 0.3, "W": 0.15, "S": 0.5},  # provisional; pilot replaces
    # trigger (docs/DETECTOR.md, steps 6-7, has the reason for every value)
    "threshold": 1.75,         # picked by the pre-registered pilot rule (>= 70% right, <= 1 false alarm per round)
    "cooldown_s": 10,          # next pop-up possible 10 s after the previous one was closed (pilot: 2nd+ all right)
    "dismiss_cooldown_s": 20,  # 20 s after "No thanks"
    "max_popups": 5,
    # second chance (Smart): no pop-up 10 s after all phones were seen -> first check with score >= 1.0
    "extra_after_s": 10,
    "extra_threshold": 1.0,
    # Random (C4): first pop-up at "all seen" + a delay drawn from YOKED_DELAYS_S; later ones at this rate
    "c4_rate_per_min": 0.43,   # Random's later pop-ups: Smart's pilot rate of 2nd+ pop-ups per minute
}

# Delays (s after all phones were seen) of Smart's first pop-up in the 13 pilot rounds that had one, with the
# settings above. Random draws its first pop-up delay from this list, so Smart and Random pop up equally often and
# at the same points in a round; only Smart is tied to the person's hesitation (a yoked control).
YOKED_DELAYS_S = [0.5, 7.0, 7.5, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 11.5, 12.5, 17.0]

# Frozen-settings revision applied once on start-up (app/db.py) and logged in the audit log. Participants keep the
# settings they started with. Revision 3 replaces the 9-14 s timers of revision 2, which fired before people had seen
# the phones and made Smart and Random identical.
SETTINGS_REVISION = 4
REVISION_NOTE = ("Revision 4: threshold 1.75 (pilot rule), detection in one check (3.5 s), second chance 10 s after "
                 "all phones seen at score >= 1.0, Random yoked to Smart's pilot timing, at-Buy pop-up in both; the "
                 "9-14 s timers removed (rev. 3). Several pop-ups per round: next one 10 s after the previous was "
                 "closed (20 s after No thanks), up to 5; Random's later pop-ups at 0.43/min (rev. 4).")
# Reading time assumed when a participant asked for help but left the answer open: ~100 words at ~240 words/min
ANSWER_READING_S = 25

THRESHOLD_GRID = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]

SELECTION_RULE = {
    "min_precision": 0.70,
    "max_false_alarms_per_task": 1.0,
    "match_margin_ms": 3000,
}

STUDY_INFO_DEFAULTS = {
    "title": "Beyond Clicks: Shopping Decisions Study",
    "team": "HTI (DS 4101) project team, Plaksha University",
    "contact": "Add team contact emails in the researcher dashboard",
    "supervisor": "Course instructor, HTI (DS 4101)",
    "irb": "Ethics approval: pending",
    "reward": "A small thank-you for taking part, plus a bonus for each correct choice.",
    "duration_pilot": "about 70 minutes",
    "duration_main": "about 75 minutes",
}

CONDITIONS = {
    "C1": {"name": "No AI", "intro": "In this round you shop on your own. There is no AI assistant."},
    "C2": {"name": "Ask AI", "intro": "In this round you can ask the AI assistant for help at any time, using the \"Ask AI\" button."},
    "C3": {"name": "Smart pop-up", "intro": "In this round an AI assistant may offer help while you shop."},
    "C4": {"name": "Random pop-up", "intro": "In this round an AI assistant may offer help while you shop."},
}

# Balanced Latin square (Williams design) for 4 conditions: each condition appears once in each
# position, and each condition follows every other condition exactly once.
WILLIAMS_ROWS = [[0, 1, 3, 2], [1, 2, 0, 3], [2, 3, 1, 0], [3, 0, 2, 1]]
COND_CODES = ["C1", "C2", "C3", "C4"]
MAIN_SETS = ["S1", "S2", "S3", "S4"]
# Cyclic Latin square for which phone set goes in which position.
CYCLIC_ROWS = [[0, 1, 2, 3], [1, 2, 3, 0], [2, 3, 0, 1], [3, 0, 1, 2]]
