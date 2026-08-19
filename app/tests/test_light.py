# app/tests/test_light.py

import pytest

from plantiq.engine.light import cardinal_of, exposure, wall_azimuth

# 10 m by 4 m, one plan unit per centimetre
ROOM = [(0, 0), (1000, 0), (1000, 400), (0, 400)]
# Wall 1 spans 400 cm; t 0.125 to 0.875 gives a 3 m opening, the reference width
WINDOW = [{"type": "window", "wall_index": 1, "t_start": 0.125, "t_end": 0.875}]
UNITS_PER_CM = 1.0


def test_east_wall_faces_east_when_north_is_up():
    assert cardinal_of(wall_azimuth(ROOM, 1, 0)) == "E"


def test_rotating_north_rotates_the_wall():
    assert cardinal_of(wall_azimuth(ROOM, 1, 270)) == "S"


@pytest.mark.parametrize(
    ("distance_m", "intensity", "level"),
    [(1.66, 0.40, "indirect"), (8.56, 0.03, "low")],
)
def test_intensity_falls_off_with_distance(distance_m, intensity, level):
    result = exposure((1000 - distance_m * 100, 200), ROOM, WINDOW, 0, UNITS_PER_CM)
    assert result.intensity == pytest.approx(intensity, abs=0.01)
    assert result.level == level


def test_a_wall_between_hides_the_window():
    l_shape = [(0, 0), (400, 0), (400, 200), (200, 200), (200, 400), (0, 400)]
    window = [{"type": "window", "wall_index": 1, "t_start": 0.2, "t_end": 0.8}]
    assert not exposure((100, 300), l_shape, window, 0, UNITS_PER_CM).visible


def test_without_calibration_the_answer_degrades_instead_of_raising():
    result = exposure((900, 200), ROOM, WINDOW, 0, None)
    assert result.intensity == 0.0
    assert result.level == "low"


# --- opening width


def test_a_three_metre_opening_is_the_reference():
    result = exposure((900, 200), ROOM, WINDOW, 0, UNITS_PER_CM)
    assert result.width_m == pytest.approx(3.0)
    # Full azimuth weight at one metre: 0.70 x 4 x 1 / 4
    assert result.intensity == pytest.approx(0.70, abs=0.01)


def test_a_narrow_opening_lets_in_proportionally_less():
    narrow = [{"type": "window", "wall_index": 1, "t_start": 0.4, "t_end": 0.65}]
    result = exposure((900, 200), ROOM, narrow, 0, UNITS_PER_CM)
    assert result.width_m == pytest.approx(1.0)
    assert result.intensity == pytest.approx(0.70 / 3, abs=0.01)


def test_a_bay_window_lets_in_more_than_the_reference():
    bay = [{"type": "window", "wall_index": 1, "t_start": 0.0, "t_end": 1.0}]
    result = exposure((900, 200), ROOM, bay, 0, UNITS_PER_CM)
    assert result.width_m == pytest.approx(4.0)
    assert result.intensity == pytest.approx(0.70 * 4 / 3, abs=0.01)


def test_width_can_change_the_level_on_its_own():
    # Same wall, same metre of distance: only the opening differs
    narrow = [{"type": "window", "wall_index": 1, "t_start": 0.45, "t_end": 0.55}]
    close = (1000 - 100, 200)
    assert exposure(close, ROOM, WINDOW, 0, UNITS_PER_CM).level == "bright_indirect"
    assert exposure(close, ROOM, narrow, 0, UNITS_PER_CM).level == "low"
