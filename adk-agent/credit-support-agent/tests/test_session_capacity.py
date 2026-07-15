import pytest

from agent.session_capacity import SessionCapacity


def test_capacity_weights_audio_and_video_sessions():
    capacity = SessionCapacity(max_units=5, audio_units=1, video_units=4)

    capacity.reserve("audio-room", "audio")
    capacity.reserve("video-room", "video")

    assert capacity.snapshot() == {
        "active_sessions": 2,
        "capacity_units_used": 5,
        "capacity_units_max": 5,
    }
    with pytest.raises(OverflowError):
        capacity.reserve("overflow", "audio")


def test_release_allows_room_replacement_without_leaking_units():
    capacity = SessionCapacity(max_units=4, audio_units=1, video_units=4)
    capacity.reserve("same-room", "video")

    released = capacity.release("same-room")
    replacement = capacity.reserve("same-room", "audio")

    assert released is not None
    assert replacement.units == 1
    assert capacity.used_units == 1


def test_duplicate_room_requires_explicit_release():
    capacity = SessionCapacity(max_units=4)
    capacity.reserve("same-room", "audio")

    with pytest.raises(ValueError, match="already has"):
        capacity.reserve("same-room", "audio")
