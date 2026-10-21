"""The ordered list of screens ("steps") each participant goes through."""
from .defaults import CONDITIONS

PILOT_INTERVIEW = [
    "Which moments or phones confused you most, and why?",
    "Which specs or words did you not understand?",
    "What kind of help would you have wanted while choosing?",
]

MAIN_INTERVIEW = [
    "What did you like or dislike about the AI help in the different rounds?",
    "Was there a moment when help came at a bad time, or when you wished help had come?",
    "Anything else you would like to tell us?",
]


def pilot_plan(set_order, ai_check):
    steps = [
        {"key": "consent", "kind": "consent"},
        {"key": "device", "kind": "device_check"},
        {"key": "intro", "kind": "instructions", "page": "pilot_intro"},
        {"key": "baseline1", "kind": "task", "task_key": "baseline1", "task_kind": "baseline1", "set": "P", "condition": "C1"},
        {"key": "baseline2", "kind": "task", "task_key": "baseline2", "task_kind": "baseline2", "set": "P", "condition": "C1"},
        {"key": "tasks_intro", "kind": "instructions", "page": "tasks_intro"},
    ]
    for i, set_id in enumerate(set_order, 1):
        tk = f"t{i}"
        steps += [
            {"key": f"{tk}_task", "kind": "task", "task_key": tk, "task_kind": "main", "position": i, "set": set_id, "condition": "C1"},
            {"key": f"{tk}_switch", "kind": "switch", "task_key": tk},
            {"key": f"{tk}_conf", "kind": "confidence", "task_key": tk},
        ]
    steps.append({"key": "replay_intro", "kind": "instructions", "page": "replay_intro"})
    for i in range(1, 5):
        steps.append({"key": f"t{i}_replay", "kind": "replay", "task_key": f"t{i}", "position": i})
    steps.append({"key": "interview", "kind": "interview", "questions": PILOT_INTERVIEW})
    if ai_check:
        steps += [
            {"key": "ai_intro", "kind": "instructions", "page": "ai_check_intro"},
            {"key": "ai_task", "kind": "task", "task_key": "ai", "task_kind": "pilot_ai", "position": 5, "set": "S5", "condition": "C3"},
            {"key": "ai_switch", "kind": "switch", "task_key": "ai"},
            {"key": "ai_feedback", "kind": "post_task", "task_key": "ai", "condition": "C3", "round": 5},
        ]
    steps.append({"key": "end", "kind": "end", "page": "pilot_end"})
    return steps


def main_plan(cond_order, set_order):
    steps = [
        {"key": "consent", "kind": "consent"},
        {"key": "device", "kind": "device_check"},
        {"key": "intro", "kind": "instructions", "page": "main_intro"},
        {"key": "baseline1", "kind": "task", "task_key": "baseline1", "task_kind": "baseline1", "set": "P", "condition": "C1"},
        {"key": "baseline2", "kind": "task", "task_key": "baseline2", "task_kind": "baseline2", "set": "P", "condition": "C1"},
        {"key": "practice", "kind": "task", "task_key": "practice", "task_kind": "practice", "set": "P", "condition": "DEMO"},
        {"key": "tasks_intro", "kind": "instructions", "page": "tasks_intro"},
    ]
    for i, (cond, set_id) in enumerate(zip(cond_order, set_order), 1):
        tk = f"t{i}"
        steps += [
            {"key": f"{tk}_intro", "kind": "condition_intro", "condition": cond, "round": i,
             "text": CONDITIONS[cond]["intro"]},
            {"key": f"{tk}_task", "kind": "task", "task_key": tk, "task_kind": "main", "position": i, "set": set_id, "condition": cond},
            {"key": f"{tk}_switch", "kind": "switch", "task_key": tk},
            {"key": f"{tk}_post", "kind": "post_task", "task_key": tk, "condition": cond, "round": i},
        ]
    for i, cond in enumerate(cond_order, 1):
        if cond != "C1":
            steps.append({"key": f"sus_{cond}", "kind": "sus", "condition": cond, "round": i})
    steps += [
        {"key": "ranking", "kind": "ranking", "rounds": [
            {"round": i, "condition": c, "text": CONDITIONS[c]["intro"]} for i, c in enumerate(cond_order, 1)]},
        {"key": "interview", "kind": "interview", "questions": MAIN_INTERVIEW},
        {"key": "debrief", "kind": "debrief"},
        {"key": "end", "kind": "end", "page": "main_end"},
    ]
    return steps
