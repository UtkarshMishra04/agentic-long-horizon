"""Solution for roboenvs/RedBoxUnderRack-v0 (run: python RedBoxUnderRack-v0.py --seed 0 [--video out.gif])."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import main  # noqa: E402
from underrack_common import solve_underrack  # noqa: E402

ENV_ID = "roboenvs/RedBoxUnderRack-v0"


def solve(agent):
    solve_underrack(agent)


if __name__ == "__main__":
    main(ENV_ID, solve)
