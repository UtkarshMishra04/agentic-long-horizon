"""Solution for roboenvs/PackRack-v2 (run: python PackRack-v2.py --seed 0 [--video out.gif])."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import main  # noqa: E402
from packrack_common import solve_packrack  # noqa: E402

ENV_ID = "roboenvs/PackRack-v2"


def solve(agent):
    solve_packrack(agent)


if __name__ == "__main__":
    main(ENV_ID, solve)
