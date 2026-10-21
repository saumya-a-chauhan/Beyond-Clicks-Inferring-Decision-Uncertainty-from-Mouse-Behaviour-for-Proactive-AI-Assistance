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
    "persistence_ticks": 4,    # score must stay >= threshold for 4 checks in a row (~2 s)
    # cursor event definitions
    "rest_speed_px_s": 50.0,   # resting = slower than 50 px/s
    "rest_point_ms": 150,      # a rest point = resting for >= 150 ms (segments moves for W)
    "visit_min_ms": 200,       # a card visit counts if >= 200 ms (Rayner 1998 fixation)
    "min_move_px": 30.0,       # wandering only counts moves with straight distance >= 30 px
    "seen_card_ms": 1000,      # "seen all phones" = each card hovered >= 1 s in total
    # z-scores
    "z_cap": 5.0,
    "min_spread": {"B": 0.5, "F": 0.3, "I": 0.3, "W": 0.15, "S": 0.5},  # provisional; pilot replaces
    # trigger
    "threshold": 1.5,          # provisional; pilot picks the final value
    "cooldown_s": 45,
    "dismiss_cooldown_s": 90,
    "max_popups": 3,
    # random pop-up condition (C4): pop-ups per minute after "seen all"; pilot replaces
    "c4_rate_per_min": 0.5,
}

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
