"""Solution for LongHorizonTAMP/RedBoxToBlueSpot-v0 (run: python RedBoxToBlueSpot-v0.py --seed 0 [--video out.gif]).

Move the blue box to a free spot, then put the red box where the blue box started. The L-stick must
stay within 1 cm of its start, so grasps pick the finger axis that keeps the fingers away from it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bluespot_common import solve_bluespot  # noqa: E402
from common import main  # noqa: E402

ENV_ID = "LongHorizonTAMP/RedBoxToBlueSpot-v0"


def solve(a):
    # The stick must stay within 1 cm of its start: it is never touched.
    solve_bluespot(a)


if __name__ == "__main__":
    main(ENV_ID, solve)
