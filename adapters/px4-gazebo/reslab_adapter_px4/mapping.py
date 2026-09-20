"""Translation of generic effects into PX4 mechanisms.

Two mechanism families exist:

- `failure`: PX4 System Failure Injection (`failure <unit> <type>` shell command,
  `MAV_CMD_INJECT_FAILURE` over MAVLink, MAVSDK `Failure` plugin). Only available in
  simulation and only when the parameter `SYS_FAILURE_EN` is set. Which unit/type
  combinations are implemented depends on the PX4 release and simulator; PX4 rejects
  unsupported combinations and the adapter reports the injection as not applied.
- `companion`: mechanisms realised by the adapter itself in its role of companion
  computer (for example dropping and re-establishing its MAVLink link to emulate a
  mission-computer restart). PX4 then reacts with its own failsafes.

Reference: PX4 user guide, "System Failure Injection" (docs/px4-integration.md lists the
upstream links).
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
    mechanism: str  # "failure" | "companion"
    unit: FailureUnit | None = None
    failure_type: FailureType | None = None
    companion_action: str | None = None
    note: str = ""

    def describe(self) -> str:
        if self.mechanism == "failure" and self.unit and self.failure_type:
            return f"px4:failure {self.unit.value.lower()} {self.failure_type.value.lower()}"
        return f"companion:{self.companion_action}"


_SENSOR_TYPES: dict[Effect, FailureType] = {
    Effect.UNAVAILABLE: FailureType.OFF,
    Effect.STUCK: FailureType.STUCK,
    Effect.ERRONEOUS: FailureType.WRONG,
    Effect.INTERMITTENT: FailureType.INTERMITTENT,
    Effect.DEGRADED: FailureType.SLOW,
}


def _sensor(unit: FailureUnit, effects: tuple[Effect, ...]) -> dict[Effect, FailureMapping]:
    return {
        effect: FailureMapping(mechanism="failure", unit=unit, failure_type=_SENSOR_TYPES[effect])
        for effect in effects
    }


MAPPINGS: dict[str, dict[Effect, FailureMapping]] = {
    "navigation.gnss": _sensor(
        FailureUnit.SENSOR_GPS,
        (Effect.UNAVAILABLE, Effect.STUCK, Effect.ERRONEOUS, Effect.INTERMITTENT, Effect.DEGRADED),
    ),
    "sensors.barometer": _sensor(
        FailureUnit.SENSOR_BARO,
        (Effect.UNAVAILABLE, Effect.STUCK, Effect.ERRONEOUS, Effect.INTERMITTENT, Effect.DEGRADED),
    ),
    "sensors.magnetometer": _sensor(
        FailureUnit.SENSOR_MAG,
        (Effect.UNAVAILABLE, Effect.STUCK, Effect.ERRONEOUS, Effect.INTERMITTENT, Effect.DEGRADED),
    ),
    "sensors.imu": _sensor(
        FailureUnit.SENSOR_GYRO, (Effect.DEGRADED, Effect.ERRONEOUS, Effect.INTERMITTENT)
    ),
    "communications.c2": {
        Effect.UNAVAILABLE: FailureMapping(
            mechanism="failure",
            unit=FailureUnit.SYSTEM_MAVLINK_SIGNAL,
            failure_type=FailureType.OFF,
            note="PX4 declares data link loss and applies NAV_DLL_ACT",
        ),
        Effect.TEMPORARY_DISCONNECT: FailureMapping(
            mechanism="failure",
            unit=FailureUnit.SYSTEM_MAVLINK_SIGNAL,
            failure_type=FailureType.OFF,
            note="cleared with failure type OK when the duration elapses",
        ),
        Effect.INTERMITTENT: FailureMapping(
            mechanism="failure",
            unit=FailureUnit.SYSTEM_MAVLINK_SIGNAL,
            failure_type=FailureType.INTERMITTENT,
        ),
    },
    "external.gcs": {
        Effect.UNAVAILABLE: FailureMapping(
            mechanism="failure",
            unit=FailureUnit.SYSTEM_MAVLINK_SIGNAL,
            failure_type=FailureType.OFF,
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
