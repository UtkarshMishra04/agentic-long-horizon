"""Solution for roboenvs/LiftRedBox-v0 (run: python LiftRedBox-v0.py --seed 0 [--video out.gif]).

The red box starts beyond reach: pull it in with the L-stick, park the stick, grasp and lift the box.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import Skills, main  # noqa: E402
from tool_common import REACH_R, fetch_far_box  # noqa: E402

ENV_ID = "roboenvs/LiftRedBox-v0"


def solve(a):
    for _attempt in range(4):
        k = Skills(a)
        if np.hypot(*a.pos("red_box")[:2]) > REACH_R:
            fetch_far_box(a, carry_z=0.2)
            continue
        if k.pick("red_box"):
            a.move([a.ee_pos[0], a.ee_pos[1], 0.45], closed=True, speed=0.02)
            a.hold(20)
        else:
            a.move([a.ee_pos[0], a.ee_pos[1], 0.3], closed=False)


if __name__ == "__main__":
    main(ENV_ID, solve)
