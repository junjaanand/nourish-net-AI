"""Tests for Crypto Audit Engine — verify SHA-256 chain integrity."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.crypto_audit import (
    canonicalize_transaction,
    compute_hash,
    compute_chain_hash,
    create_rescue_receipt,
    verify_single_receipt,
    verify_chain_integrity,
    get_liability_shield_status,
    generate_certificate_html,
)


def test_canonicalize():
    """Same data in different order should produce same canonical form."""
    d1 = {"b": 2, "a": 1, "c": 3}
    d2 = {"c": 3, "a": 1, "b": 2}
    assert canonicalize_transaction(d1) == canonicalize_transaction(d2)
    print("✅ Canonicalization is deterministic")


def test_hash_determinism():
    h1 = compute_hash("hello world")
    h2 = compute_hash("hello world")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex = 64 chars
    print(f"✅ SHA-256 deterministic: {h1[:24]}…")


def test_chain_hash():
    data = {"food": "rice", "qty": 10}
    h = compute_chain_hash(data, "GENESIS")
    assert len(h) == 64
    # Different previous hash → different chain hash
    h2 = compute_chain_hash(data, "DIFFERENT")
    assert h != h2
    print("✅ Chain hash depends on previous hash")


def _make_sample_receipt():
    donation = {"id": 1, "donor_name": "Test Hotel", "food_category": "fruits",
                "quantity_kg": 20, "prep_time": "2026-10-17T12:00:00", "latitude": 19.0, "longitude": 72.8}
    ngo = {"id": 1, "name": "Test NGO", "org_type": "kitchen", "beneficiary_count": 500,
           "latitude": 19.1, "longitude": 72.9}
    match = {"id": 1, "composite_score": 0.85, "distance_km": 12.5, "eta_minutes": 35}
    return create_rescue_receipt(donation, ngo, match, 25.0, 23.0, "GENESIS")


def test_create_receipt():
    receipt = _make_sample_receipt()
    assert receipt["chain_hash"]
    assert receipt["previous_hash"] == "GENESIS"
    assert receipt["match_id"] == 1
    print(f"✅ Receipt created: hash={receipt['chain_hash'][:24]}…")


def test_verify_receipt():
    receipt = _make_sample_receipt()
    assert verify_single_receipt(receipt), "Receipt should verify"
    print("✅ Receipt verification passed")

    # Tamper with the receipt
    tampered = dict(receipt)
    tampered["pickup_temp"] = 99.9  # This doesn't affect the hash (it's separate)
    # But tampering with transaction_data should break it
    tampered2 = dict(receipt)
    tampered2["transaction_data"] = {**receipt["transaction_data"], "tampered": True}
    assert not verify_single_receipt(tampered2), "Tampered receipt should fail"
    print("✅ Tamper detection works")


def test_chain_integrity():
    donation = {"id": 1, "donor_name": "D1", "food_category": "fruits",
                "quantity_kg": 10, "prep_time": "2026-10-17T12:00:00", "latitude": 19.0, "longitude": 72.8}
    ngo = {"id": 1, "name": "N1", "org_type": "kitchen", "beneficiary_count": 500,
           "latitude": 19.1, "longitude": 72.9}

    chain = []
    prev_hash = "GENESIS"
    for i in range(5):
        match = {"id": i + 1, "composite_score": 0.8, "distance_km": 10, "eta_minutes": 30}
        receipt = create_rescue_receipt(donation, ngo, match, 25, 23, prev_hash)
        chain.append(receipt)
        prev_hash = receipt["chain_hash"]

    result = verify_chain_integrity(chain)
    assert result["valid"], "Valid chain should verify"
    assert result["total_records"] == 5
    print(f"✅ Chain of 5 records verified: {result['message']}")


def test_liability_compliant():
    receipt = {"transaction_data": {"temperature_chain": {
        "pickup_celsius": 25, "delivery_celsius": 23, "chain_maintained": True}}}
    status = get_liability_shield_status(receipt)
    assert status["status"] == "COMPLIANT"
    print(f"✅ Liability shield: {status['badge']}")


def test_liability_warning():
    receipt = {"transaction_data": {"temperature_chain": {
        "pickup_celsius": 25, "delivery_celsius": 40, "chain_maintained": False}}}
    status = get_liability_shield_status(receipt)
    assert status["status"] == "WARNING"
    print(f"✅ Liability warning: {status['badge']}")


def test_certificate_html():
    donation = {"id": 1, "donor_name": "Hotel", "food_category": "fruits",
                "quantity_kg": 20, "prep_time": "2026-10-17T12:00:00", "latitude": 19.0, "longitude": 72.8}
    ngo = {"id": 1, "name": "NGO", "org_type": "kitchen", "beneficiary_count": 500,
           "latitude": 19.1, "longitude": 72.9}
    match = {"id": 1, "composite_score": 0.85, "distance_km": 12.5, "eta_minutes": 35}

    receipt = create_rescue_receipt(donation, ngo, match, 25, 23, "GENESIS")
    html = generate_certificate_html(receipt)
    assert "NourishNet AI" in html
    assert receipt["chain_hash"] in html
    print(f"✅ Certificate HTML generated ({len(html)} chars)")


if __name__ == "__main__":
    test_canonicalize()
    test_hash_determinism()
    test_chain_hash()
    test_verify_receipt()
    test_chain_integrity()
    test_liability_compliant()
    test_liability_warning()
    test_certificate_html()
    print("\n🎉 All crypto audit tests passed!")
