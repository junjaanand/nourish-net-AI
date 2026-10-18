"""Tests for Spoilage Engine — verify Arrhenius calculations."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.spoilage_engine import (
    calculate_spoilage_time,
    get_urgency_level,
    get_freshness_percentage,
    get_decay_curve,
    get_urgency_color,
)


def test_basic_spoilage():
    """Hot meals at high temp should spoil faster."""
    t1 = calculate_spoilage_time("cooked_hot_meals", 35, 50, "sealed")
    t2 = calculate_spoilage_time("cooked_hot_meals", 5, 50, "sealed")
    assert t1 < t2, f"Higher temp should spoil faster: {t1} vs {t2}"
    print(f"✅ Hot meals @ 35°C: {t1:.0f} min vs @ 5°C: {t2:.0f} min")


def test_packaging_effect():
    """Vacuum packaging should extend shelf life vs open."""
    t_open = calculate_spoilage_time("fruits", 25, 50, "open")
    t_vacuum = calculate_spoilage_time("fruits", 25, 50, "vacuum")
    assert t_vacuum > t_open, "Vacuum should last longer than open"
    print(f"✅ Fruits open: {t_open:.0f} min vs vacuum: {t_vacuum:.0f} min")


def test_humidity_effect():
    """Higher humidity should accelerate spoilage."""
    t_dry = calculate_spoilage_time("leafy_greens", 25, 30, "sealed")
    t_humid = calculate_spoilage_time("leafy_greens", 25, 90, "sealed")
    assert t_dry > t_humid, "Dry should last longer than humid"
    print(f"✅ Greens @ 30% humidity: {t_dry:.0f} min vs @ 90%: {t_humid:.0f} min")


def test_urgency_levels():
    assert get_urgency_level(30) == "CRITICAL"
    assert get_urgency_level(120) == "URGENT"
    assert get_urgency_level(300) == "NORMAL"
    assert get_urgency_level(600) == "STABLE"
    print("✅ Urgency levels correct")


def test_freshness():
    f = get_freshness_percentage("bakery_bread", 0, 25, 50, "sealed")
    assert f == 100.0, f"Fresh bread should be 100%: {f}"
    print(f"✅ Fresh bread: {f}%")


def test_decay_curve():
    curve = get_decay_curve("fruits", 25, 50, "sealed", duration_hours=12)
    assert len(curve) > 0
    assert curve[0]["freshness_pct"] == 100.0
    print(f"✅ Decay curve: {len(curve)} points, starts at {curve[0]['freshness_pct']}%")


def test_urgency_colors():
    assert get_urgency_color("CRITICAL") == "#FF4444"
    assert get_urgency_color("STABLE") == "#4488FF"
    print("✅ Urgency colors correct")


def test_all_categories():
    """Every food category should return a positive spoilage time."""
    cats = ["cooked_hot_meals", "fresh_dairy", "leafy_greens", "bakery_bread",
            "canned_packaged", "fruits", "frozen_items"]
    for cat in cats:
        t = calculate_spoilage_time(cat, 25, 50, "sealed")
        assert t > 0, f"{cat} should have positive spoilage time"
    print(f"✅ All {len(cats)} categories produce valid spoilage times")


if __name__ == "__main__":
    test_basic_spoilage()
    test_packaging_effect()
    test_humidity_effect()
    test_urgency_levels()
    test_freshness()
    test_decay_curve()
    test_urgency_colors()
    test_all_categories()
    print("\n🎉 All spoilage engine tests passed!")
