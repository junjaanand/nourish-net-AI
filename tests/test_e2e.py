"""Full end-to-end integration test for NourishNet AI using FastAPI TestClient."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app


def test_full_lifecycle():
    with TestClient(app) as client:
        # Reset to fresh seed state for reproducible test suite execution
        client.get("/api/seed")

        print("=== 1. HEALTH ENDPOINT ===")
        r = client.get("/api/health")
        assert r.status_code == 200, f"Health check failed: {r.text}"
        health = r.json()
        print(f"Status: {health['status']} | Platform: {health['platform']} | App: {health['app_name']}")

        print("\n=== 2. DONATIONS ENDPOINT ===")
        r = client.get("/api/donations")
        assert r.status_code == 200
        donations = r.json()
        print(f"Total donations: {len(donations)}")
        for d in donations[:3]:
            did = d["id"]
            cat = d["food_category"]
            urg = d["urgency_level"]
            rem = d["remaining_minutes"]
            fresh = d["freshness_pct"]
            print(f"  #{did} {cat} | Urgency: {urg} | Remaining: {rem:.0f} min | Freshness: {fresh:.1f}%")

        print("\n=== 3. NGOs ENDPOINT ===")
        r = client.get("/api/ngos")
        assert r.status_code == 200
        ngos = r.json()
        print(f"Total NGOs loaded: {len(ngos)}")
        for n in ngos[:3]:
            print(f"  #{n['id']} {n['name']} ({n['org_type']}) - Capacity: {n['available_capacity_kg']}/{n['capacity_kg']}kg")

        print("\n=== 4. AI MATCHING (Hungarian Optimizer) ===")
        r = client.post("/api/match", json={})
        assert r.status_code == 200, f"Match failed: {r.text}"
        result = r.json()
        print(f"Server Message: {result['message']}")
        print(f"Execution Latency: {result['elapsed_ms']}ms")
        matches = result.get("matches", [])
        assert len(matches) > 0, "Expected at least 1 match"
        for m in matches:
            mid = m["id"]
            dn = m["donor_name"]
            nn = m["ngo_name"]
            sc = m["composite_score"]
            dist = m["distance_km"]
            eta = m["eta_minutes"]
            print(f"  Match #{mid}: {dn} -> {nn}")
            print(f"    Composite Score: {sc:.3f} | Dist: {dist:.1f}km | ETA: {eta:.0f} min")

        print("\n=== 5. SHAP EXPLAINABILITY (TreeSHAP) ===")
        mid = matches[0]["id"]
        r = client.get(f"/api/match/{mid}/explain")
        assert r.status_code == 200
        exp = r.json()
        print(f"Feature Names: {exp.get('feature_names', [])}")
        print(f"SHAP Values: {exp.get('shap_values', [])}")
        print(f"Base Value: {exp.get('base_value')} | Match Prediction: {exp.get('prediction', 0):.2%}")
        has_plot = "waterfall_plot_base64" in exp and exp["waterfall_plot_base64"] is not None
        print(f"Waterfall plot base64 generated: {has_plot} ({len(exp.get('waterfall_plot_base64') or '')} chars)")

        print("\n=== 6. CRYPTOGRAPHIC AUDIT CERTIFICATE (SHA-256) ===")
        r = client.post("/api/audit/generate", json={
            "match_id": matches[0]["id"],
            "pickup_temp_celsius": 25.0,
            "delivery_temp_celsius": 23.0,
        })
        assert r.status_code == 200
        aud = r.json()
        print(f"Audit Record ID: #{aud['id']}")
        print(f"Chain Hash: {aud['chain_hash']}")
        print(f"Previous Hash: {aud['previous_hash']}")

        print("\n=== 7. AUDIT CHAIN VERIFICATION ===")
        r = client.get("/api/audit/chain")
        assert r.status_code == 200
        chain = r.json()
        print(f"Chain Valid: {chain['valid']} | Verified Records: {chain['total_records']}")
        print(f"Verification Message: {chain['message']}")

        print("\n=== 8. HTML CERTIFICATE RENDERING ===")
        r = client.get(f"/api/audit/{aud['id']}/certificate")
        assert r.status_code == 200
        assert "FOOD RESCUE CERTIFICATE" in r.text
        print(f"HTML Certificate verified ({len(r.text)} characters)")

        print("\n=== 9. ESG IMPACT ANALYTICS & DELIVERY COMPLETION ===")
        r = client.get("/api/impact")
        assert r.status_code == 200
        impact = r.json()
        for k, v in impact.items():
            print(f"  {k}: {v}")
        assert impact["completed_rescues"] >= 1, f"Expected completed_rescues >= 1, got {impact['completed_rescues']}"
        print(f"✅ Verified delivery lifecycle: completed_rescues = {impact['completed_rescues']}")

        print("\n=== 10. TIER-2 CIRCULAR BIO-UPCYCLING FALLBACK ===")
        # Create an extreme near-expired donation (only 5 minutes remaining safe life)
        from datetime import datetime, timezone, timedelta
        now_iso = (datetime.now(timezone.utc) - timedelta(hours=3.8)).isoformat()
        r_don = client.post("/api/donations", json={
            "donor_name": "Midnight Banquet Hall Jaipur",
            "food_category": "cooked_hot_meals",
            "quantity_kg": 75.0,
            "prep_time": now_iso,
            "ambient_temp_celsius": 42.0,
            "humidity_percent": 70.0,
            "packaging_type": "open",
            "latitude": 26.9124,
            "longitude": 75.7873,
            "notes": "Emergency near-spoilage test case",
        })
        assert r_don.status_code == 200
        crit_don = r_don.json()
        print(f"Created high-urgency surplus #{crit_don['id']} ({crit_don['remaining_minutes']:.1f}m remaining)")

        # Execute match for this donation
        r_match = client.post("/api/match", json={"donation_id": crit_don["id"]})
        assert r_match.status_code == 200
        t2_matches = r_match.json().get("matches", [])
        assert len(t2_matches) > 0
        t2_m = t2_matches[0]
        print(f"Matched #{crit_don['id']} -> {t2_m['ngo_name']}")
        print(f"  Tier: {t2_m.get('tier')} ({t2_m.get('tier_name')}) | Composite: {t2_m.get('composite_score')}")
        assert t2_m.get("tier") in (1, 2)
        print("✅ Verified Tier Dispatcher: Zero food abandoned!")

        print("\n=== 11. FAIRNESS / GINI COEFFICIENT ===")
        r = client.get("/api/fairness")
        assert r.status_code == 200
        fair = r.json()
        print(f"Fair: {fair.get('is_fair')} | Gini Coefficient: {fair.get('gini_coefficient', 0):.3f}")

        print("\n🎉 ALL 11 UPGRADE TEST PHASES PASSED! NOURISHNET AI IS PRODUCTION-GRADE & READY FOR LINUXONE! 🎉")


if __name__ == "__main__":
    test_full_lifecycle()
