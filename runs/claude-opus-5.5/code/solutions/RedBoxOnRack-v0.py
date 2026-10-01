"""Solution for roboenvs/RedBoxOnRack-v0 (run: python RedBoxOnRack-v0.py --seed 0 [--video out.gif]).

The red box starts beyond reach: pull it in with the L-stick, park the stick, then pick the box and
place it on the centre of the rack top.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import Skills, main  # noqa: E402
from tool_common import REACH_R, fetch_far_box  # noqa: E402

ENV_ID = "roboenvs/RedBoxOnRack-v0"


def solve(a):
    for _attempt in range(4):
        k = Skills(a)
        if np.hypot(*a.pos("red_box")[:2]) > REACH_R:
            fetch_far_box(a, carry_z=0.2)
            continue
        if k.pick("red_box"):
            k.place("red_box", a.pos("rack")[:2], a.pos("rack")[2], a.yaw("rack"))
            a.hold(20)
        else:
            a.move([a.ee_pos[0], a.ee_pos[1], 0.3], closed=False)


if __name__ == "__main__":
    main(ENV_ID, solve)
