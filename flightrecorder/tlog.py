from __future__ import annotations

import math
from pathlib import Path

from .model import FlightSample


def read_tlog(path: str | Path) -> list[FlightSample]:
    """Convert selected Mission Planner MAVLink messages to normalized samples.

    MAVLink messages arrive at different rates. We therefore keep the latest
    value from every message type and emit a snapshot whenever useful telemetry
    arrives. This is called state reconstruction.
    """

    try:
        from pymavlink import mavutil
    except ImportError as error:
        raise RuntimeError(
            "pymavlink is required for .tlog import; run: python -m pip install pymavlink"
        ) from error

    connection = mavutil.mavlink_connection(str(path), robust_parsing=True)
    state = FlightSample()
    samples: list[FlightSample] = []
    first_timestamp: float | None = None
    useful = {"GLOBAL_POSITION_INT", "VFR_HUD", "ATTITUDE", "SYS_STATUS", "HEARTBEAT"}

    while True:
        message = connection.recv_match(blocking=False)
        if message is None:
            break
        kind = message.get_type()
        if kind == "BAD_DATA" or kind not in useful:
            continue
        timestamp = float(getattr(message, "_timestamp", 0.0))
        if first_timestamp is None:
            first_timestamp = timestamp
        state.time_s = max(0.0, timestamp - first_timestamp)

        if kind == "GLOBAL_POSITION_INT":
            state.latitude_deg = message.lat / 1e7
            state.longitude_deg = message.lon / 1e7
            state.relative_altitude_m = message.relative_alt / 1000.0
            state.groundspeed_m_s = math.hypot(message.vx, message.vy) / 100.0
            state.climb_rate_m_s = -message.vz / 100.0
            if message.hdg != 65535:
                state.yaw_deg = message.hdg / 100.0
        elif kind == "VFR_HUD":
            state.airspeed_m_s = float(message.airspeed)
            state.groundspeed_m_s = float(message.groundspeed)
            state.throttle_pct = float(message.throttle)
            state.climb_rate_m_s = float(message.climb)
        elif kind == "ATTITUDE":
            state.roll_deg = math.degrees(message.roll)
            state.pitch_deg = math.degrees(message.pitch)
            state.yaw_deg = math.degrees(message.yaw) % 360.0
        elif kind == "SYS_STATUS":
            if message.voltage_battery != 65535:
                state.battery_voltage_v = message.voltage_battery / 1000.0
            if message.current_battery != -1:
                state.battery_current_a = message.current_battery / 100.0
            if message.battery_remaining != -1:
                state.battery_remaining_pct = float(message.battery_remaining)
        elif kind == "HEARTBEAT":
            state.armed = bool(message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            state.mode = mavutil.mode_string_v10(message)

        samples.append(FlightSample(**state.to_dict()))

    if not samples:
        raise ValueError("No supported MAVLink telemetry was found in the .tlog")
    return samples

