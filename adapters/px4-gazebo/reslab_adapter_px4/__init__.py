"""PX4 SITL + Gazebo adapter.

The adapter talks MAVLink to a PX4 SITL instance (MAVSDK transport) and realises generic
scenario effects with PX4's supported simulation failure injection
(`MAV_CMD_INJECT_FAILURE`, requires `SYS_FAILURE_EN=1`) plus companion-side mechanisms.
Nothing here models a physical disturbance; see docs/em-resilience.md.
"""

from reslab_adapter_px4.adapter import PX4_ADAPTER_VERSION, PX4_CAPABILITIES, PX4GazeboAdapter
from reslab_adapter_px4.mapping import FailureMapping, mapping_for

__all__ = [
    "PX4_ADAPTER_VERSION",
    "PX4_CAPABILITIES",
    "FailureMapping",
    "PX4GazeboAdapter",
    "mapping_for",
]
