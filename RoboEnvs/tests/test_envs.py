"""Every environment builds, resets, steps and exposes consistent spaces, state and goal."""

import numpy as np
import pytest

import roboenvs

EXPECTED_OBJECTS = {
    "roboenvs/LiftRedBox-v0": 3,
    "roboenvs/RedBoxOnRack-v0": 3,
    "roboenvs/RedBoxUnderRack-v0": 3,
    "roboenvs/RedBoxUnderRack-v1": 3,
    "roboenvs/RedBoxToBlueSpot-v0": 3,
    "roboenvs/RedBoxToBlueSpot-v1": 3,
    "roboenvs/PackRack-v0": 4,
    "roboenvs/PackRack-v1": 4,
    "roboenvs/PackRack-v2": 5,
}


@pytest.mark.parametrize("env_id", sorted(roboenvs.ENV_IDS))
@pytest.mark.parametrize("control", ["delta", "absolute"])
def test_env(env_id, control):
    env = roboenvs.make(env_id, control=control)
    try:
        seeds = []
        for seed in (1, 2):
            observation, info = env.reset(seed=seed)
            assert set(observation) == set(env.observation_space.spaces)
            for key, space in env.observation_space.spaces.items():
                assert observation[key].shape == space.shape and observation[key].dtype == space.dtype, key
            assert info["step"] == 0 and info["success"] is False and info["scene_seed"] >= seed
            seeds.append(info["scene_seed"])
            state = env.get_state()
            num_gripper = env.observation_space["robot0_gripper_qpos"].shape[0]
            assert state.dtype == np.float32
            assert state.shape == (7 + 7 + num_gripper + 7 + 7 * EXPECTED_OBJECTS[env_id],)
            goal = env.get_goal()
            assert isinstance(goal["text"], str) and goal["text"] and goal["conditions"]
            assert all("text" in c and "type" in c and "objects" in c for c in goal["conditions"])
            for _ in range(30):
                action = env.action_space.sample()
                observation, reward, terminated, truncated, info = env.step(action)
                assert reward in (0.0, 1.0) and terminated == (reward == 1.0)
            assert info["step"] == 30
            assert env.render().shape == (256, 256, 3)
        # The same seed reproduces the same scene.
        env.reset(seed=1)
        first = env.get_state()
        env.reset(seed=1)
        np.testing.assert_allclose(env.get_state(), first, atol=1e-5)
    finally:
        env.close()


def test_time_limit():
    env = roboenvs.make("roboenvs/PackRack-v0", max_episode_steps=5)
    try:
        env.reset(seed=3)
        for _ in range(5):
            _, _, terminated, truncated, _ = env.step(np.zeros(7))
        assert truncated and not terminated
    finally:
        env.close()
