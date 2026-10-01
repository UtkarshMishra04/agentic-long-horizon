"""Builds the site's data files from the episode replays (python3 build_data.py <replay_out_dir>).

Writes data/episodes/<agent>_<env>_<seed>.js (one per recorded video, loaded on demand) and
data/catalog.js (list of episodes with their outcome and video timing). Standard library only.
"""

import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STRIDE = 2  # keep every 2nd control step (plus the last)

# How each agent's video maps playback frames to control steps.
VIDEO = {
    "codex": {"fps": 20, "steps_per_frame": 1, "dir": "media/codex"},
    "claude": {"fps": 10, "steps_per_frame": 4, "dir": "media/claude"},
}


def r3(values):
    return [round(v, 3) for v in values]


def detect_events(ep):
    """Gripper closes/opens (with the object involved), first lift and first unheld motion of each object, goal."""
    events = []
    grip = ep["grip"]
    lo, hi = min(grip), max(grip)
    names = list(ep["objects"])
    ee = ep["ee"]

    def nearest(i):
        best, dist = None, 1e9
        for n in names:
            o = ep["objects"][n]
            d = math.dist((o["x"][i], o["y"][i], o["z"][i]), (ee["x"][i], ee["y"][i], ee["z"][i]))
            if d < dist:
                best, dist = n, d
        return best, dist

    if hi - lo > 0.05:
        mid = 0.5 * (lo + hi)
        closed = grip[0] > mid
        for i in range(1, len(grip)):
            now = grip[i] > mid
            if now != closed:
                obj, dist = nearest(i)
                near = obj if dist < 0.12 else None
                if now:
                    text = f"gripper closes on {near}" if near else "gripper closes"
                else:
                    text = f"gripper opens, releasing {near}" if near else "gripper opens"
                events.append({"step": i, "kind": "close" if now else "open", "text": text, "object": near})
                closed = now
    for n in names:
        o = ep["objects"][n]
        z0, x0, y0 = o["z"][0], o["x"][0], o["y"][0]
        lifted = next((i for i, z in enumerate(o["z"]) if z - z0 > 0.03), None)
        if lifted is not None:
            events.append({"step": lifted, "kind": "lift", "text": f"{n} lifted off its support", "object": n})
        moved = next(
            (i for i in range(len(o["x"])) if math.hypot(o["x"][i] - x0, o["y"][i] - y0) > 0.02 and abs(o["z"][i] - z0) < 0.02),
            None,
        )
        if moved is not None and (lifted is None or moved < lifted):
            events.append({"step": moved, "kind": "slide", "text": f"{n} starts sliding on the table", "object": n})
    if ep["success_step"] is not None:
        events.append({"step": ep["success_step"], "kind": "goal", "text": "goal reached (reward 1.0)", "object": None})
    events.sort(key=lambda e: e["step"])
    return events


def main(replay_dir):
    os.makedirs(os.path.join(HERE, "data", "episodes"), exist_ok=True)
    catalog = []
    for path in sorted(glob.glob(os.path.join(replay_dir, "*.json"))):
        ep = json.load(open(path))
        if "agent" not in ep:
            continue
        n = ep["steps"] + 1
        keep = list(range(0, n, STRIDE))
        if keep[-1] != n - 1:
            keep.append(n - 1)
        sub = lambda arr: r3([arr[i] for i in keep])  # noqa: E731
        events = detect_events(ep)
        video = VIDEO[ep["agent"]]
        eid = f"{ep['agent']}_{ep['env']}_{ep['seed']}"
        data = {
            "id": eid,
            "agent": ep["agent"],
            "env": ep["env"],
            "seed": ep["seed"],
            "scene_seed": ep["scene_seed"],
            "steps": ep["steps"],
            "success": ep["success"],
            "success_step": ep["success_step"],
            "goal": ep["goal"],
            "t": keep,
            "ee": {k: sub(v) for k, v in ep["ee"].items()},
            "grip": sub(ep["grip"]),
            "grip_range": [min(ep["grip"]), max(ep["grip"])],
            "objects": {
                name: {k: (sub(v) if k != "tilt" else [round(v[i], 0) for i in keep]) for k, v in o.items()}
                for name, o in ep["objects"].items()
            },
            "events": events,
        }
        with open(os.path.join(HERE, "data", "episodes", eid + ".js"), "w") as f:
            f.write("window.__episode(" + json.dumps(data, separators=(",", ":")) + ");\n")
        catalog.append(
            {
                "id": eid,
                "agent": ep["agent"],
                "env": ep["env"],
                "seed": ep["seed"],
                "scene_seed": ep["scene_seed"],
                "steps": ep["steps"],
                "success": ep["success"],
                "success_step": ep["success_step"],
                "video": f"{video['dir']}/{ep['env']}_seed{ep['seed']}.mp4",
                "fps": video["fps"],
                "steps_per_frame": video["steps_per_frame"],
                "goal_text": ep["goal"]["text"],
                "n_events": len(events),
            }
        )
    with open(os.path.join(HERE, "data", "catalog.js"), "w") as f:
        f.write("window.CATALOG = " + json.dumps(catalog, indent=1) + ";\n")
    print(len(catalog), "episodes")


if __name__ == "__main__":
    main(sys.argv[1])
