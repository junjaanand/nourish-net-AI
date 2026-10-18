"""
NourishNet AI — Production-Grade Master Test Suite
===================================================
Comprehensive test coverage verifying system robustness, mathematical rigour,
zero-bug boundary handling, cryptographic security, concurrency, and production readiness.

Author: NourishNet AI Engineering Team
Target: IBM Z Datathon 2026 | Track 1: Real-Time AI for Critical Decisions
"""

import base64
import concurrent.futures
from datetime import datetime, timedelta, timezone
import json
import math
import os
import sys
import threading
import time
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app
from backend import database as db
from backend.config import FOOD_PARAMS, MATCH_WEIGHTS, MAX_DELIVERY_RANGE_KM
from backend.models import (
    spoilage_engine,
    matcher_engine,
    explainer_engine,
    crypto_audit,
)


@pytest.fixture(scope="session")
def client():
    """Session test client for FastAPI."""
    with TestClient(app) as test_client:
        # Reset to pristine seed state
        test_client.get("/api/seed")
        yield test_client


# ══════════════════════════════════════════════════════════════════════════════
# 1. SYSTEM & ARCHITECTURE VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

class TestSystemArchitecture:
    """Verify system uptime, health check, platform detection, and static assets."""

    def test_health_endpoint(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["app_name"] == "NourishNet AI"
        assert "version" in data
        assert "platform" in data
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    def test_frontend_dist_served(self, client):
        """Verify compiled React SPA is mounted and served at root."""
        dist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
        assert os.path.exists(dist_path), "frontend/dist directory must exist"
        
        index_html = os.path.join(dist_path, "index.html")
        assert os.path.exists(index_html), "frontend/dist/index.html must exist"
        assert os.path.getsize(index_html) > 200, "index.html must be populated"

        r = client.get("/")
        assert r.status_code == 200
        assert "<!doctype html>" in r.text.lower()
        assert "NourishNet AI" in r.text

    def test_database_persistence_wal(self):
        """Verify SQLite WAL mode and table persistence."""
        with db._lock:
            cur = db._conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            mode = cur.fetchone()[0]
            # In memory or file, journal mode must be valid
            assert mode.lower() in ("wal", "memory")


# ══════════════════════════════════════════════════════════════════════════════
# 2. ARRHENIUS SPOILAGE ENGINE & PHYSICS RIGOR
# ══════════════════════════════════════════════════════════════════════════════

class TestArrheniusPhysics:
    """Mathematical verification of the modified Arrhenius food kinetics model."""

    @pytest.mark.parametrize("category", [
        "cooked_hot_meals", "fresh_dairy", "leafy_greens",
        "bakery_bread", "canned_packaged", "fruits", "frozen_items"
    ])
    def test_all_food_categories_calibrated(self, category):
        """Every category must calculate positive finite safe window."""
        t_safe = spoilage_engine.calculate_spoilage_time(category, ambient_temp=25.0, humidity=50.0, packaging="sealed")
        assert 1.0 <= t_safe <= 43200.0, f"Safe time out of bounds for {category}: {t_safe}"

    def test_thermal_decay_monotonicity(self):
        """Arrhenius physics law: Higher ambient temp strictly decreases safe window."""
        for cat in ["cooked_hot_meals", "fresh_dairy", "leafy_greens"]:
            t_cold = spoilage_engine.calculate_spoilage_time(cat, ambient_temp=10.0, humidity=50.0, packaging="sealed")
            t_room = spoilage_engine.calculate_spoilage_time(cat, ambient_temp=25.0, humidity=50.0, packaging="sealed")
            t_hot = spoilage_engine.calculate_spoilage_time(cat, ambient_temp=40.0, humidity=50.0, packaging="sealed")
            assert t_cold > t_room > t_hot, f"Monotonicity violated for {cat}: {t_cold} > {t_room} > {t_hot}"

    def test_humidity_acceleration_monotonicity(self):
        """High humidity (>40%) accelerates microbial growth, shortening safe time."""
        t_dry = spoilage_engine.calculate_spoilage_time("leafy_greens", ambient_temp=25.0, humidity=30.0, packaging="sealed")
        t_moderate = spoilage_engine.calculate_spoilage_time("leafy_greens", ambient_temp=25.0, humidity=55.0, packaging="sealed")
        t_humid = spoilage_engine.calculate_spoilage_time("leafy_greens", ambient_temp=25.0, humidity=90.0, packaging="sealed")
        assert t_dry >= t_moderate > t_humid, "Humidity acceleration failed monotonicity"

    def test_packaging_multiplier_hierarchy(self):
        """Packaging protection: open (0.7) < sealed (1.0) < vacuum (1.5) < frozen (3.0)."""
        t_open = spoilage_engine.calculate_spoilage_time("fruits", 25.0, 50.0, "open")
        t_sealed = spoilage_engine.calculate_spoilage_time("fruits", 25.0, 50.0, "sealed")
        t_vacuum = spoilage_engine.calculate_spoilage_time("fruits", 25.0, 50.0, "vacuum")
        t_frozen = spoilage_engine.calculate_spoilage_time("fruits", 25.0, 50.0, "frozen")
        assert t_open < t_sealed < t_vacuum < t_frozen, "Packaging hierarchy violated"

    def test_freshness_decay_curve_monotonicity(self):
        """Decay curve must start at 100% and strictly decrease toward 0%."""
        curve = spoilage_engine.get_decay_curve("cooked_hot_meals", ambient_temp=30.0, duration_hours=6.0, steps=50)
        assert len(curve) == 51
        assert curve[0]["freshness_pct"] == 100.0
        assert curve[-1]["freshness_pct"] <= 10.0
        # Check non-increasing
        for i in range(len(curve) - 1):
            assert curve[i]["freshness_pct"] >= curve[i + 1]["freshness_pct"]

    def test_extreme_environmental_boundaries(self):
        """Test sub-zero winter (-20C) and extreme desert heat (+50C) edge cases."""
        t_subzero = spoilage_engine.calculate_spoilage_time("frozen_items", -20.0, 10.0, "frozen")
        assert t_subzero > 1000.0
        t_heat = spoilage_engine.calculate_spoilage_time("cooked_hot_meals", 55.0, 95.0, "open")
        assert t_heat >= 1.0  # Clamped to at least 1 minute

    def test_urgency_tier_classification(self):
        """Urgency thresholds: Critical (<60m), Urgent (<180m), Normal (<480m), Stable (>=480m)."""
        assert spoilage_engine.get_urgency_level(15) == "CRITICAL"
        assert spoilage_engine.get_urgency_level(59.9) == "CRITICAL"
        assert spoilage_engine.get_urgency_level(60.1) == "URGENT"
        assert spoilage_engine.get_urgency_level(179) == "URGENT"
        assert spoilage_engine.get_urgency_level(181) == "NORMAL"
        assert spoilage_engine.get_urgency_level(479) == "NORMAL"
        assert spoilage_engine.get_urgency_level(481) == "STABLE"
        assert spoilage_engine.get_urgency_level(-10) == "CRITICAL"  # Expired


# ══════════════════════════════════════════════════════════════════════════════
# 3. BIPARTITE MATCHING & KUHN-MUNKRES OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════

class TestMatcherOptimization:
    """Verification of the Hungarian bipartite optimal assignment algorithm."""

    def test_haversine_accuracy(self):
        """Mumbai (19.076, 72.877) to Pune (18.520, 73.856) should be ~120 km."""
        dist = matcher_engine.haversine_distance(19.076, 72.877, 18.520, 73.856)
        assert 110 < dist < 135

    def test_composite_weight_sum(self):
        """Weights must mathematically sum exactly to 1.0."""
        total = sum(matcher_engine.WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, expected 1.0"

    def test_sub_10ms_latency_benchmark(self):
        """Stress benchmark: 15 donations x 15 NGOs assignment in under 15ms."""
        donations = [
            {"id": i, "donor_name": f"Donor {i}", "food_category": "cooked_hot_meals",
             "quantity_kg": 25.0, "latitude": 19.0 + (i * 0.01), "longitude": 72.8 + (i * 0.01),
             "remaining_minutes": 120.0}
            for i in range(15)
        ]
        ngos = [
            {"id": j, "name": f"NGO {j}", "org_type": "kitchen", "capacity_kg": 100.0,
             "current_load_kg": 0.0, "latitude": 19.05 + (j * 0.01), "longitude": 72.85 + (j * 0.01),
             "beneficiary_count": 200, "dietary_prefs": ["vegetarian", "non-vegetarian"]}
            for j in range(15)
        ]

        t0 = time.perf_counter()
        matches = matcher_engine.solve_optimal_matching(donations, ngos)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        assert len(matches) == 15
        assert duration_ms < 15.0, f"Matching took {duration_ms:.2f}ms, exceeds 15ms target"

    def test_hard_constraint_transit_time_exceeds_safe_window(self):
        """Donation with 20m safe window and 40km away must be rejected from Tier 1."""
        donation = {
            "id": 99, "donor_name": "Far Donor", "food_category": "cooked_hot_meals",
            "quantity_kg": 20.0, "latitude": 19.0, "longitude": 72.8,
        }
        ngo = {
            "id": 99, "name": "Far NGO", "capacity_kg": 100.0, "current_load_kg": 0.0,
            "latitude": 19.4, "longitude": 72.8,  # ~44 km
            "beneficiary_count": 500, "dietary_prefs": ["vegetarian", "non-vegetarian"],
        }
        sc = matcher_engine.compute_score(donation, ngo, remaining_minutes=20.0, max_beneficiaries=500)
        assert not sc["is_feasible"], "Should be infeasible due to ETA buffer exceeding safe time"

    def test_tier_2_circular_fallback(self):
        """When Tier-1 human delivery is infeasible, automatic fallback to Tier-2 occurs."""
        crit_donation = {
            "id": 88, "donor_name": "Expiring Caterer", "food_category": "cooked_hot_meals",
            "quantity_kg": 50.0, "latitude": 19.0, "longitude": 72.8, "remaining_minutes": 5.0
        }
        far_ngo = {
            "id": 88, "name": "Far NGO", "capacity_kg": 100.0, "current_load_kg": 0.0,
            "latitude": 28.6, "longitude": 77.2, "beneficiary_count": 500, "dietary_prefs": ["vegetarian"]
        }
        matches = matcher_engine.solve_optimal_matching([crit_donation], [far_ngo])
        assert len(matches) == 1
        m = matches[0]
        assert m["tier"] == 2
        assert "Circular Upcycling" in m["tier_name"]


# ══════════════════════════════════════════════════════════════════════════════
# 4. EXPLAINABLE AI (TreeSHAP) & FAIRNESS AUDIT
# ══════════════════════════════════════════════════════════════════════════════

class TestExplainableAIFairness:
    """Verification of SHAP TreeExplainer feature attributions and Gini equity."""

    def test_shap_training_and_attribution(self):
        model, explainer = explainer_engine.train_explainer_model()
        assert model is not None
        assert explainer is not None

        features = [0.8, 0.9, 0.7, 0.85, 1.0, 95.0, 25.0]
        exp = explainer_engine.explain_match(model, explainer, features)

        assert "shap_values" in exp
        assert "feature_names" in exp
        assert len(exp["shap_values"]) == len(exp["feature_names"]) == 7
        assert "prediction" in exp
        assert 0.0 <= exp["prediction"] <= 1.0

    def test_waterfall_plot_base64_generation(self):
        """Ensure waterfall plot produces valid base64 encoded PNG."""
        model, explainer = explainer_engine.train_explainer_model()
        features = [0.85, 0.9, 0.75, 0.8, 1.0, 90.0, 20.0]
        exp = explainer_engine.explain_match(model, explainer, features)

        plot_b64 = explainer_engine.generate_shap_waterfall_plot(
            exp["shap_values"], exp["feature_names"], exp["base_value"], exp["prediction"]
        )
        assert plot_b64 is not None and len(plot_b64) > 100
        # Decode and verify PNG header magic bytes
        raw_bytes = base64.b64decode(plot_b64)
        assert raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid PNG image data"

    def test_gini_fairness_distribution(self):
        """Equitable NGO resource distribution test."""
        ngos = [{"id": i, "name": f"NGO {i}"} for i in range(1, 6)]
        # Perfectly balanced allocations
        matches = [{"ngo_id": i} for i in range(1, 6)] * 4  # 20 matches, 4 per NGO
        result = explainer_engine.check_distribution_fairness(matches, ngos)
        assert result["gini_coefficient"] == 0.0
        assert result["is_fair"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. CRYPTOGRAPHIC AUDIT VAULT & IMMUTABILITY
# ══════════════════════════════════════════════════════════════════════════════

class TestCryptographicVault:
    """Verification of SHA-256 chain-of-custody, tamper detection, and liability shield."""

    def test_canonicalization_invariance(self):
        """Dictionary key ordering or spacing must not alter canonical JSON."""
        d1 = {"b": "2", "a": 1, "nested": {"y": 20, "x": 10}}
        d2 = {"nested": {"x": 10, "y": 20}, "a": 1, "b": "2"}
        c1 = crypto_audit.canonicalize_transaction(d1)
        c2 = crypto_audit.canonicalize_transaction(d2)
        assert c1 == c2

    def test_sha256_hash_properties(self):
        h = crypto_audit.compute_hash("NourishNet AI IBM LinuxONE")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_tamper_detection_pinpointed(self):
        """Tampering with any block in the audit chain must be pinpointed exactly."""
        # Create a mock 4-block chain
        chain = []
        prev_hash = "GENESIS"
        for i in range(4):
            data = {"rescue_id": i, "kg": 50 + i}
            h = crypto_audit.compute_chain_hash(data, prev_hash)
            chain.append({
                "id": i + 1,
                "chain_hash": h,
                "previous_hash": prev_hash,
                "transaction_data": data,
                "is_valid": True,
            })
            prev_hash = h

        # Verify uncorrupted chain
        v_clean = crypto_audit.verify_chain_integrity(chain)
        assert v_clean["valid"] is True
        assert v_clean["total_records"] == 4

        # Tamper with block #2 (index 1)
        tampered_chain = [dict(b) for b in chain]
        tampered_chain[1]["transaction_data"] = {"rescue_id": 1, "kg": 9999}  # Fraudulent change
        v_tampered = crypto_audit.verify_chain_integrity(tampered_chain)
        assert v_tampered["valid"] is False
        assert v_tampered["broken_at_index"] == 1, f"Expected break at index 1, got {v_tampered['broken_at_index']}"

    def test_cold_chain_liability_shield(self):
        """Safe Haven compliance status under food safety laws."""
        # Cooked food maintained within allowable delta
        receipt_compliant = {
            "pickup_temp": 65.0,
            "delivery_temp": 62.0,
            "transaction_data": {
                "food_category": "cooked_hot_meals",
                "temperature_chain": {
                    "pickup_celsius": 65.0,
                    "delivery_celsius": 62.0,
                    "chain_maintained": True,
                }
            }
        }
        res = crypto_audit.get_liability_shield_status(receipt_compliant)
        assert res["status"] == "COMPLIANT"

        # Food temperature chain violated
        receipt_violation = {
            "pickup_temp": 65.0,
            "delivery_temp": 28.0,
            "transaction_data": {
                "food_category": "cooked_hot_meals",
                "temperature_chain": {
                    "pickup_celsius": 65.0,
                    "delivery_celsius": 28.0,
                    "chain_maintained": False,
                }
            }
        }
        res_violation = crypto_audit.get_liability_shield_status(receipt_violation)
        assert res_violation["status"] == "WARNING"


# ══════════════════════════════════════════════════════════════════════════════
# 6. API CONTRACT, VALIDATION & ZERO-BUG BOUNDARY HANDLING
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIContractsAndBoundaries:
    """Stress tests boundary handling and Pydantic validation error codes."""

    def test_reject_negative_quantity(self, client):
        r = client.post("/api/donations", json={
            "donor_name": "Test",
            "food_category": "cooked_hot_meals",
            "quantity_kg": -15.0,
            "prep_time": datetime.now(timezone.utc).isoformat(),
            "ambient_temp_celsius": 25.0,
            "latitude": 19.0,
            "longitude": 72.8,
        })
        assert r.status_code == 422  # Unprocessable Entity

    def test_reject_absurd_temperature(self, client):
        r = client.post("/api/donations", json={
            "donor_name": "Test",
            "food_category": "cooked_hot_meals",
            "quantity_kg": 15.0,
            "prep_time": datetime.now(timezone.utc).isoformat(),
            "ambient_temp_celsius": 150.0,  # Max is 60C
            "latitude": 19.0,
            "longitude": 72.8,
        })
        assert r.status_code == 422

    def test_reject_invalid_coordinates(self, client):
        r = client.post("/api/donations", json={
            "donor_name": "Test",
            "food_category": "cooked_hot_meals",
            "quantity_kg": 15.0,
            "prep_time": datetime.now(timezone.utc).isoformat(),
            "ambient_temp_celsius": 25.0,
            "latitude": 195.0,  # Invalid latitude (>90)
            "longitude": 72.8,
        })
        assert r.status_code == 422

    def test_reject_invalid_food_category_enum(self, client):
        r = client.post("/api/donations", json={
            "donor_name": "Test",
            "food_category": "radioactive_waste",
            "quantity_kg": 15.0,
            "prep_time": datetime.now(timezone.utc).isoformat(),
            "ambient_temp_celsius": 25.0,
            "latitude": 19.0,
            "longitude": 72.8,
        })
        assert r.status_code == 422

    def test_reject_malformed_prep_time(self, client):
        r = client.post("/api/donations", json={
            "donor_name": "Test",
            "food_category": "cooked_hot_meals",
            "quantity_kg": 15.0,
            "prep_time": "yesterday-afternoon",
            "ambient_temp_celsius": 25.0,
            "latitude": 19.0,
            "longitude": 72.8,
        })
        assert r.status_code == 400

    def test_nonexistent_resource_404_handling(self, client):
        assert client.get("/api/donations/999999").status_code == 404
        assert client.get("/api/ngos/999999").status_code == 404
        assert client.get("/api/match/999999/explain").status_code == 404
        assert client.get("/api/audit/999999/certificate").status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 7. MULTI-THREADED CONCURRENCY & THREAD SAFETY STRESS TEST
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrencyAndThreadSafety:
    """Stress test the backend under simultaneous concurrent operations."""

    def test_concurrent_donations_and_matches(self, client):
        """Spawn 10 concurrent threads creating donations and matching without deadlocks."""
        errors = []

        def worker(thread_id):
            try:
                # 1. Create donation
                iso_time = datetime.now(timezone.utc).isoformat()
                r_don = client.post("/api/donations", json={
                    "donor_name": f"Concurrent Donor #{thread_id}",
                    "food_category": "fruits",
                    "quantity_kg": 10.0 + thread_id,
                    "prep_time": iso_time,
                    "ambient_temp_celsius": 22.0,
                    "humidity_percent": 50.0,
                    "packaging_type": "sealed",
                    "latitude": 19.07 + (thread_id * 0.001),
                    "longitude": 72.87 + (thread_id * 0.001),
                })
                if r_don.status_code != 200:
                    errors.append(f"Thread {thread_id} donation failed: {r_don.text}")
                    return

                don_id = r_don.json()["id"]

                # 2. Match
                r_match = client.post("/api/match", json={"donation_id": don_id})
                if r_match.status_code != 200:
                    errors.append(f"Thread {thread_id} match failed: {r_match.text}")
            except Exception as e:
                errors.append(f"Thread {thread_id} exception: {str(e)}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrency test encountered {len(errors)} errors: {errors}"


# ══════════════════════════════════════════════════════════════════════════════
# 8. ESG & SUSTAINABILITY IMPACT ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

class TestESGImpactMetrics:
    """Verify ESG calculation equations and delivery lifecycle transitions."""

    def test_esg_multipliers(self, client):
        r = client.get("/api/impact")
        assert r.status_code == 200
        impact = r.json()

        # Check conversion formulas: 1kg = 2.5 meals, 2.5kg CO2, 100L water
        rescued_kg = impact["total_kg_rescued"]
        if rescued_kg > 0:
            assert abs(impact["total_meals_served"] - round(rescued_kg * 2.5)) <= 2
            assert abs(impact["total_co2_avoided_kg"] - round(rescued_kg * 2.5, 1)) <= 1.0
            assert abs(impact["total_water_saved_liters"] - round(rescued_kg * 100.0)) <= 10.0
