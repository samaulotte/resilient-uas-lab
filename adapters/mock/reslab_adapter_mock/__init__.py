"""Deterministic mock adapter.

The mock is an explicit simulator: every value it produces comes from a seeded,
step-based model of a multirotor with a companion computer. It exists so the whole
platform can be exercised, demonstrated and tested without PX4 or Gazebo.
"""

from reslab_adapter_mock.adapter import MOCK_ADAPTER_VERSION, MOCK_CAPABILITIES, MockAdapter
from reslab_adapter_mock.simulation import MockSimulation

__all__ = ["MOCK_ADAPTER_VERSION", "MOCK_CAPABILITIES", "MockAdapter", "MockSimulation"]
