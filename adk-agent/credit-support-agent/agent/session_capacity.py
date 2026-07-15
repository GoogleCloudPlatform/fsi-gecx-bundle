"""In-process capacity accounting for audio and avatar voice sessions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapacityReservation:
    room_name: str
    mode: str
    units: int


class SessionCapacity:
    """Reserve bounded runtime units without mixing room ownership."""

    def __init__(self, *, max_units: int, audio_units: int = 1, video_units: int = 4):
        if min(max_units, audio_units, video_units) < 1:
            raise ValueError("Session capacity values must be positive")
        self.max_units = max_units
        self._mode_units = {"audio": audio_units, "video": video_units}
        self._reservations: dict[str, CapacityReservation] = {}

    @property
    def used_units(self) -> int:
        return sum(item.units for item in self._reservations.values())

    @property
    def active_sessions(self) -> int:
        return len(self._reservations)

    def release(self, room_name: str) -> CapacityReservation | None:
        return self._reservations.pop(room_name, None)

    def reserve(self, room_name: str, mode: str) -> CapacityReservation:
        if room_name in self._reservations:
            raise ValueError(f"Room {room_name!r} already has a capacity reservation")
        try:
            units = self._mode_units[mode]
        except KeyError as error:
            raise ValueError(f"Unsupported session mode: {mode}") from error
        if self.used_units + units > self.max_units:
            raise OverflowError(
                f"Session needs {units} capacity units; "
                f"{self.max_units - self.used_units} remain"
            )
        reservation = CapacityReservation(room_name=room_name, mode=mode, units=units)
        self._reservations[room_name] = reservation
        return reservation

    def snapshot(self) -> dict[str, int]:
        return {
            "active_sessions": self.active_sessions,
            "capacity_units_used": self.used_units,
            "capacity_units_max": self.max_units,
        }
