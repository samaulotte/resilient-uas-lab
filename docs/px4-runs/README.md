# PX4 SITL run evidence

These are canonical reports (`report.json`, schema 1.0) captured from real runs of the
`px4-gazebo` adapter against live PX4 v1.18.0-rc1 with Gazebo Harmonic (MAVSDK 3.17.4),
executed both directly through the engine and through the full Compose `sim` stack. They
are committed as evidence for the PX4 validation described in
[`../px4-integration.md`](../px4-integration.md); regenerate them by reproducing a run as
that document explains.

| File | Result | Score | Injections applied | Notes |
| ---- | ------ | ----- | ------------------ | ----- |
| `gnss-loss.report.json` | passed | 97.4 | 1 | GPS aiding removed at T+35, estimator degraded, PX4 position failsafe, recovery ~2.4 s after aiding restored |
| `mission-compute-restart.report.json` | passed | 82.2 | 1 | Companion link dropped and re-established, mission compute recovered ~5.8 s later, flight domain untouched |
| `compound-degradation.report.json` | passed | 74.2 | 3 | Sequential GNSS loss, datalink loss and compute restart; GNSS failsafe to LAND then resume to MISSION |

The reports record `software_version` and `adapter_version` `0.1.0`: they were captured
on the working tree that became commits `dec2cb4` (metrics), `c601e14` (connectivity)
and `23d19c5` (fault mechanisms), before the version was raised to `0.2.0`. That code is
what shipped in `0.2.0`; only the version literals changed afterwards. The
`INJECTION_APPLIED` events in the reports name the shipped mechanism (`EKF2_GPS_CTRL`).

Each run passes the three critical assertions (flight control available, no loss of
control, flight domain contained). The high and medium assertions that do not hold
(`mission.completion`, `mission.completed`, and one recovery-time bound) reflect real
differences between PX4 and the mock: PX4's failsafes curtail the mission and real-time
flight is slower than the mock. Those outcomes are reported, not hidden.
