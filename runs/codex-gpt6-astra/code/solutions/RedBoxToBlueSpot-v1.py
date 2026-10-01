"""Run the deterministic public-interface controller for RedBoxToBlueSpot-v1."""
import argparse
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from controllers import episode

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    print(json.dumps(episode("RedBoxToBlueSpot-v1", args.seed, args.verbose)))
