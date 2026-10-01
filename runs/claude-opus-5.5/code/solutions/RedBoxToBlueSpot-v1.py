"""Solution for LongHorizonTAMP/RedBoxToBlueSpot-v1 (run: python RedBoxToBlueSpot-v1.py --seed 0 [--video out.gif]).

The red box starts beyond reach: pull it in with the L-stick and park the stick in the workspace away
from both boxes and from the blue box's start; then move the blue box away and put the red box there.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bluespot_common import solve_bluespot  # noqa: E402
from common import Skills, main  # noqa: E402
from tool_common import fetch_far_box  # noqa: E402

ENV_ID = "LongHorizonTAMP/RedBoxToBlueSpot-v1"


def stick_in_workspace(center, yaw):
    return center[0] >= 0.43 and np.hypot(center[0], center[1]) < 0.72


def solve(a):
    target = np.array(
        [c for c in a.goal["conditions"] if c["type"] == "pos" and c["objects"][0] == "red_box"][0]["target_xy"]
    )
    def fetch(name):
        fetch_far_box(a, name, keep_out=[(target, 0.1)], valid=stick_in_workspace, hard_keep_out=True)

    def repark():
        k = Skills(a)
        k.grasp_stick(-0.05, a.yaw("lstick"))
        keep = [(target, 0.1)] + [(a.pos(n)[:2], 0.06) for n in ("red_box", "blue_box")]
        k.park_stick(keep_out=keep, valid=stick_in_workspace, hard_keep_out=True)

    solve_bluespot(a, fetch=fetch, repark=repark)


if __name__ == "__main__":
    main(ENV_ID, solve)
