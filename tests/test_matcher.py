"""Tests for Matcher Engine — verify Hungarian algorithm and scoring."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.matcher_engine import (
    haversine_distance,
    estimate_eta_minutes,
    compute_score,
    match_single_donation,
    solve_optimal_matching,
)


def test_haversine():
    """Mumbai to Delhi should be ~1150 km."""
    d = haversine_distance(19.0760, 72.8777, 28.6139, 77.2090)
    assert 1100 < d < 1200, f"Mumbai-Delhi should be ~1150 km, got {d:.0f}"
    print(f"✅ Mumbai → Delhi: {d:.0f} km")


def test_haversine_same_point():
    d = haversine_distance(19.0760, 72.8777, 19.0760, 72.8777)
    assert d < 0.01, f"Same point distance should be ~0, got {d}"
    print(f"✅ Same point: {d:.4f} km")


def test_eta():
    eta = estimate_eta_minutes(30)  # 30 km
    expected = (30 / 30) * 60 + 10  # 60 + 10 = 70 min
    assert abs(eta - expected) < 1, f"ETA for 30km should be ~70 min, got {eta}"
    print(f"✅ ETA for 30 km: {eta:.0f} min")


def test_score_nearby():
    """Nearby donation-NGO pair should score well."""
    donation = {
        "id": 1, "donor_name": "Test Donor", "food_category": "fruits",
        "quantity_kg": 20, "latitude": 19.076, "longitude": 72.877,
    }
    ngo = {
        "id": 1, "name": "Test NGO", "capacity_kg": 100, "current_load_kg": 0,
        "latitude": 19.08, "longitude": 72.88,
        "dietary_prefs": ["vegetarian", "non-vegetarian"],
        "beneficiary_count": 500,
    }
    sc = compute_score(donation, ngo, remaining_minutes=120, max_beneficiaries=500)
    assert sc["is_feasible"], "Nearby pair should be feasible"
    assert sc["proximity_score"] > 0.9, f"Very nearby should have high proximity: {sc['proximity_score']}"
    print(f"✅ Nearby score: {sc['composite_score']:.3f}, proximity: {sc['proximity_score']:.3f}")


def test_infeasible_expired():
    """Food with 5 min left and 30 km distance should be infeasible."""
    donation = {
        "id": 1, "donor_name": "Test", "food_category": "cooked_hot_meals",
        "quantity_kg": 10, "latitude": 19.076, "longitude": 72.877,
    }
    ngo = {
        "id": 1, "name": "Far NGO", "capacity_kg": 100, "current_load_kg": 0,
        "latitude": 19.3, "longitude": 73.1,  # ~30+ km away
        "dietary_prefs": ["non-vegetarian"],
        "beneficiary_count": 200,
    }
    sc = compute_score(donation, ngo, remaining_minutes=5, max_beneficiaries=200)
    assert not sc["is_feasible"], "Should be infeasible — ETA > remaining time"
    print(f"✅ Infeasible pair correctly rejected (ETA={sc['eta_minutes']:.0f} > 5 min)")


def test_single_match():
    donation = {
        "id": 1, "donor_name": "Hotel", "food_category": "cooked_hot_meals",
        "quantity_kg": 25, "remaining_minutes": 120,
        "latitude": 19.076, "longitude": 72.877,
    }
    ngos = [
        {"id": 1, "name": "Near NGO", "capacity_kg": 100, "current_load_kg": 0,
         "latitude": 19.08, "longitude": 72.88, "dietary_prefs": ["non-vegetarian"],
         "beneficiary_count": 500},
        {"id": 2, "name": "Far NGO", "capacity_kg": 100, "current_load_kg": 0,
         "latitude": 28.6, "longitude": 77.2, "dietary_prefs": ["non-vegetarian"],
         "beneficiary_count": 300},
    ]
    result = match_single_donation(donation, ngos)
    assert result is not None
    assert result["ngo_id"] == 1, "Should match to nearest NGO"
    print(f"✅ Single match: {result['donor_name']} → {result['ngo_name']} (score={result['composite_score']:.3f})")


def test_batch_matching():
    donations = [
        {"id": 1, "donor_name": "D1", "food_category": "fruits", "quantity_kg": 10,
         "remaining_minutes": 200, "latitude": 19.076, "longitude": 72.877},
        {"id": 2, "donor_name": "D2", "food_category": "bakery_bread", "quantity_kg": 15,
         "remaining_minutes": 500, "latitude": 12.971, "longitude": 77.594},
    ]
    ngos = [
        {"id": 1, "name": "N1", "capacity_kg": 100, "current_load_kg": 0,
         "latitude": 19.08, "longitude": 72.88, "dietary_prefs": ["vegetarian"],
         "beneficiary_count": 400},
        {"id": 2, "name": "N2", "capacity_kg": 200, "current_load_kg": 0,
         "latitude": 12.98, "longitude": 77.60, "dietary_prefs": ["vegetarian"],
         "beneficiary_count": 600},
    ]
    results = solve_optimal_matching(donations, ngos)
    assert len(results) == 2, f"Should match 2 pairs, got {len(results)}"
    print(f"✅ Batch match: {len(results)} pairs matched")
    for r in results:
        print(f"   {r['donor_name']} → {r['ngo_name']} (score={r['composite_score']:.3f})")


if __name__ == "__main__":
    test_haversine()
    test_haversine_same_point()
    test_eta()
    test_score_nearby()
    test_infeasible_expired()
    test_single_match()
    test_batch_matching()
    print("\n🎉 All matcher engine tests passed!")
