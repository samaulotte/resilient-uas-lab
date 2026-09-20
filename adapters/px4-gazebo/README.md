# reslab-adapter-px4

PX4 SITL + Gazebo adapter for Resilient UAS Lab.

- Transport: MAVLink through MAVSDK-Python (`transport.py`, `MavsdkLink`). The link is an
  interface (`PX4Link`) so the adapter logic is unit-tested with an in-memory fake.
- Effects: `mapping.py` translates generic scenario effects into PX4 System Failure
  Injection (`MAV_CMD_INJECT_FAILURE`, needs `SYS_FAILURE_EN=1`, simulation only) or into
  companion-side mechanisms (dropping and re-establishing the MAVLink link to emulate a
  mission-computer restart). Anything PX4 rejects is reported as *not applied*; nothing is
  silently assumed.
- States: derived from PX4 telemetry and health (GPS fix, position estimate validity,
  flight mode, battery). Components the adapter cannot observe stay `UNKNOWN` and do not
  count against availability metrics.

See `docs/px4-integration.md` for the simulation profile, the upstream references and the
current limitations. The adapter depends on `reslab-adapter-mock` only for the default
mission geometry (`planned_path_for`).
