"""Translation of generic effects into PX4 mechanisms that produce OBSERVABLE behaviour.

The design rule for this adapter is empirical: an effect is only advertised for PX4 when
it produces a change ResLab can actually observe over MAVLink on the reference image
(see docs/px4-integration.md for what was measured). Three mechanism families are used:

- `param`: remove an aiding source from the EKF by clearing a control parameter
  (`EKF2_GPS_CTRL`, `EKF2_BARO_CTRL`, `EKF2_MAG_TYPE`). This injects the *effect* of a
  sensor becoming unavailable to the estimator: the EKF stops fusing it, the affected
  estimate degrades, and the loss is observable through the vehicle health flags and
  PX4's own failsafe reaction. The original value is read before injection and restored
  on clear.
- `companion`: mechanisms realised by the adapter in its role as companion computer /
  ground link, by dropping and re-establishing its MAVLink link. PX4 then reacts with
  its real data-link-loss failsafe (`NAV_DLL_ACT`), which was measured to drive the
  vehicle into Return-To-Launch.
- `failure`: PX4 System Failure Injection (`MAV_CMD_INJECT_FAILURE`). On the reference
  Gazebo image this command is accepted but the simulated sensors do not honour it, so
  it is not used to claim an observable effect. The transport keeps the capability for
  builds where it is wired, and any injection PX4 does not realise is reported as such.

The `param` mechanism realises the *consequence* of losing a sensor (the estimator can
no longer use it); it never models a physical cause. This is the project's scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from reslab_core.scenario.catalog import Effect


class FailureUnit(StrEnum):
    """MAVSDK `FailureUnit` names (kept as strings so tests do not import MAVSDK)."""

    SENSOR_GYRO = "SENSOR_GYRO"
    SENSOR_ACCEL = "SENSOR_ACCEL"
    SENSOR_MAG = "SENSOR_MAG"
    SENSOR_BARO = "SENSOR_BARO"
    SENSOR_GPS = "SENSOR_GPS"
    SYSTEM_BATTERY = "SYSTEM_BATTERY"
    SYSTEM_MOTOR = "SYSTEM_MOTOR"
    SYSTEM_RC_SIGNAL = "SYSTEM_RC_SIGNAL"
    SYSTEM_MAVLINK_SIGNAL = "SYSTEM_MAVLINK_SIGNAL"


class FailureType(StrEnum):
    OK = "OK"
    OFF = "OFF"
    STUCK = "STUCK"
    GARBAGE = "GARBAGE"
    WRONG = "WRONG"
    SLOW = "SLOW"
    DELAYED = "DELAYED"
    INTERMITTENT = "INTERMITTENT"


@dataclass(frozen=True)
class FailureMapping:
    mechanism: str  # "param" | "companion" | "failure"
    # param mechanism
    param_name: str | None = None
    param_off_value: int | None = None
    # companion mechanism
    companion_action: str | None = None
    # failure mechanism (kept for builds where it is wired)
    unit: FailureUnit | None = None
    failure_type: FailureType | None = None
    note: str = ""

    def describe(self) -> str:
        if self.mechanism == "param" and self.param_name:
            return f"px4:param {self.param_name}={self.param_off_value}"
        if self.mechanism == "failure" and self.unit and self.failure_type:
            return f"px4:failure {self.unit.value.lower()} {self.failure_type.value.lower()}"
        return f"companion:{self.companion_action}"


def _param(name: str, off: int, note: str) -> FailureMapping:
    return FailureMapping(mechanism="param", param_name=name, param_off_value=off, note=note)


# Only (subsystem, effect) pairs that produce a MEASURED observable effect on the
# reference image are listed. Anything not here is reported as unsupported before the run
# starts, so a scenario never silently assumes an effect it cannot realise.
MAPPINGS: dict[str, dict[Effect, FailureMapping]] = {
    "navigation.gnss": {
        Effect.UNAVAILABLE: _param(
            "EKF2_GPS_CTRL",
            0,
            "removes GPS aiding from the EKF; global position estimate is lost",
        ),
        Effect.DEGRADED: _param(
            "EKF2_GPS_CTRL",
            0,
            "removes GPS aiding from the EKF; global position estimate is lost",
        ),
    },
    "sensors.barometer": {
        Effect.UNAVAILABLE: _param(
            "EKF2_BARO_CTRL", 0, "removes barometer aiding from the EKF height estimate"
        ),
        Effect.ERRONEOUS: _param(
            "EKF2_BARO_CTRL", 0, "removes barometer aiding from the EKF height estimate"
        ),
        Effect.STUCK: _param(
            "EKF2_BARO_CTRL", 0, "removes barometer aiding from the EKF height estimate"
        ),
    },
    "sensors.magnetometer": {
        Effect.UNAVAILABLE: _param(
            "EKF2_MAG_TYPE", 5, "disables magnetometer fusion (EKF2_MAG_TYPE=5, none)"
        ),
        Effect.STUCK: _param(
            "EKF2_MAG_TYPE", 5, "disables magnetometer fusion (EKF2_MAG_TYPE=5, none)"
        ),
    },
    "communications.c2": {
        Effect.UNAVAILABLE: FailureMapping(
            mechanism="companion",
            companion_action="link_down",
            note="the adapter drops its GCS link; PX4 declares data-link loss (NAV_DLL_ACT)",
        ),
    },
    "external.gcs": {
        Effect.UNAVAILABLE: FailureMapping(
            mechanism="companion",
            companion_action="link_down",
            note="ground station silence is indistinguishable from link loss for the vehicle",
        ),
    },
    "mission.compute": {
        Effect.RESTART: FailureMapping(
            mechanism="companion",
            companion_action="link_restart",
            note="the adapter drops its MAVLink link and reconnects after the restart time",
        ),
        Effect.CRASH: FailureMapping(
            mechanism="companion",
            companion_action="link_crash",
            note="link dropped, watchdog delay, then reconnect",
        ),
        Effect.UNAVAILABLE: FailureMapping(
            mechanism="companion",
            companion_action="link_down",
            note="link dropped until the effect is cleared",
        ),
    },
}


def mapping_for(subsystem: str, effect: Effect) -> FailureMapping | None:
    return MAPPINGS.get(subsystem, {}).get(effect)


def supported_effects() -> dict[str, tuple[Effect, ...]]:
    return {subsystem: tuple(effects) for subsystem, effects in MAPPINGS.items()}
