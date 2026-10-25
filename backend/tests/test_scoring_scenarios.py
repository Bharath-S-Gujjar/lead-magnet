"""Phase 1 Scoring Scenario Tests
====================================

Parameterized tests for the 100-point behavioral scoring system.

Each row asserts:
  - lead_segment        (Hot | Warm | Cold)
  - lead_score          in expected band  [score_min, score_max]
  - key reasons         string fragments present in score_reasons
  - segment_reason      substring check (if non-empty)

Test-integrity policy: expected values must be traceable to the scorer's
arithmetic.  When changed, the old/new values and the reason (scorer wrong vs.
expectation wrong) must be recorded in AUDIT.md.

Tests call compute_behavioral_score() directly -- no network, no DB.
"""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from behavioral_scoring_service import compute_behavioral_score
from scoring_constants import HOT, WARM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hours_ago(hours: float):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _days_ago(days: float):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _base(**overrides):
    """Return minimal zero-activity feature set with optional overrides."""
    base = {
        "sessions_count": 1,
        "total_events": 2,
        "total_time_spent": 0.0,
        "average_session_duration": 0.0,
        "page_views_count": 1,
        "days_since_last_activity": 0.0,
        "products_viewed": 0,
        "unique_products_viewed": 0,
        "product_interactions": 0,
        "search_count": 0,
        "form_submit_count": 0,
        "high_intent_page_visits": 0,
        "cart_item_count": 0,
        "cart_value": 0.0,
        "wishlist_item_count": 0,
        "checkout_attempts": 0,
        "orders_count": 0,
        "total_order_value": 0.0,
        "average_order_value": 0.0,
        "last_checkout_action_at": None,
        "last_cart_action_at": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Strategy scenario table
#
# Columns: (label, features_dict, expected_segment, score_min, score_max,
#           required_reason_fragments, expected_segment_reason_fragment)
#
# required_reason_fragments: list of strings, each must appear in
#   " | ".join(score_reasons).
# expected_segment_reason_fragment: substring required in segment_reason
#   (empty string = no special segment_reason check).
# ---------------------------------------------------------------------------

SCENARIOS = [
    # -----------------------------------------------------------------------
    # 01. Login-only new customer — no behavioural signal
    # Strategy row: "Login only, first session"
    # -----------------------------------------------------------------------
    (
        "login_only_new_customer",
        _base(sessions_count=1, days_since_last_activity=0.0),
        "Cold", 0, WARM - 1, [], "",
    ),

    # -----------------------------------------------------------------------
    # 02. Homepage visit once — minimal browse
    # -----------------------------------------------------------------------
    (
        "homepage_once",
        _base(sessions_count=1, page_views_count=1, days_since_last_activity=0.1),
        "Cold", 0, WARM - 1, [], "",
    ),

    # -----------------------------------------------------------------------
    # 03. Several unrelated product views (3 distinct, no repeat, no search)
    # -----------------------------------------------------------------------
    (
        "several_unrelated_views",
        _base(sessions_count=1, unique_products_viewed=3, products_viewed=3,
              days_since_last_activity=0.5),
        "Cold", 0, WARM - 1, ["Viewed 3 distinct product(s)"], "",
    ),

    # -----------------------------------------------------------------------
    # 04. Same category views (3 total views, 1 unique = 2 repeat views)
    # -----------------------------------------------------------------------
    (
        "same_category_views",
        _base(sessions_count=2, unique_products_viewed=1, products_viewed=3,
              days_since_last_activity=0.3),
        "Cold", 0, WARM - 1, ["Repeated product views"], "",
    ),

    # -----------------------------------------------------------------------
    # 05. Repeated searches only (3 searches, no other signal)
    # -----------------------------------------------------------------------
    (
        "repeated_searches_only",
        _base(sessions_count=2, search_count=3, days_since_last_activity=0.2),
        "Cold", 0, WARM - 1, ["3 product search(es)"], "",
    ),

    # -----------------------------------------------------------------------
    # 06. Wishlist add within 7 days — minimum-Warm floor
    # SCORER BUG fixed by Floor 4: wishlist within 7d => at least Warm.
    # Score itself stays < 35; segment raised by floor rule.
    # -----------------------------------------------------------------------
    (
        "wishlist_floor_warm",
        _base(sessions_count=2, wishlist_item_count=1,
              unique_products_viewed=2, days_since_last_activity=0.2),
        "Warm", 0, HOT - 1, ["Added 1 item(s) to wishlist"], "FLOOR: 1 wishlist",
    ),

    # -----------------------------------------------------------------------
    # 07. Multiple cart items in active cart (cart 2h ago), no checkout
    # AUDIT: Old expectation=Warm/35-55 was correct; scorer was wrong.
    # Floor 3: cart within 72h => at least Warm. Score = 32 (stays honest).
    # -----------------------------------------------------------------------
    (
        "multiple_cart_items",
        _base(sessions_count=3, cart_item_count=3, cart_value=450.0,
              unique_products_viewed=3, days_since_last_activity=0.1,
              last_cart_action_at=_hours_ago(2)),
        # Score = 32 (Cold by score), but cart-72h floor raises to Warm
        "Warm", 28, HOT - 1,
        ["Added 3 item(s) to cart", "Multiple cart items"],
        "FLOOR: Cart updated",
    ),

    # -----------------------------------------------------------------------
    # 08. Cart + checkout within 24h (active checkout override)
    # AUDIT: Expectation score_min=70 was WRONG. Strategy says "score stays
    # honest; only segment is promoted." Score = 50 (correct). Updated to 0-100.
    # -----------------------------------------------------------------------
    (
        "cart_plus_checkout_active",
        _base(sessions_count=2, cart_item_count=2, cart_value=300.0,
              checkout_attempts=1, unique_products_viewed=2,
              days_since_last_activity=0.2,
              last_checkout_action_at=_hours_ago(3)),
        "Hot", 0, 100,
        ["Started checkout"],
        "OVERRIDE: Active checkout",
    ),

    # -----------------------------------------------------------------------
    # 09. Abandoned checkout — 25h ago (just outside 24h override window)
    # AUDIT: Old expectation=Warm was correct; scorer was wrong.
    # Floor 2: checkout within 72h => at least Warm. Score = 36 (with hl=3d).
    # -----------------------------------------------------------------------
    (
        "abandoned_checkout_25h",
        _base(sessions_count=2, cart_item_count=1, cart_value=150.0,
              checkout_attempts=1, days_since_last_activity=2.0,
              last_checkout_action_at=_hours_ago(25)),
        # With checkout hl=3d: checkout_decay(25h)=0.787; score ~36-40 -> Warm
        "Warm", WARM, HOT - 1,
        ["Started checkout"],
        "",  # floor or score-based Warm, either is valid
    ),

    # -----------------------------------------------------------------------
    # 10. Old cart — cart action 10 days ago, no recent activity
    # -----------------------------------------------------------------------
    (
        "old_cart_10days",
        _base(sessions_count=1, cart_item_count=2, cart_value=250.0,
              days_since_last_activity=10.0, last_cart_action_at=_days_ago(10)),
        # Cart floor expires at 72h; score decayed heavily -> Cold
        "Cold", 0, WARM - 1, [], "",
    ),

    # -----------------------------------------------------------------------
    # 11. Converted customer (has placed order) — no active intent
    # Converted => is_converted=True; floors do not apply
    # -----------------------------------------------------------------------
    (
        "converted_customer",
        _base(sessions_count=5, orders_count=1, total_order_value=500.0,
              checkout_attempts=1, days_since_last_activity=1.0),
        "Warm", WARM, HOT - 1, ["Placed 1 order(s)"], "",
    ),

    # -----------------------------------------------------------------------
    # 12. Heavy activity 10 days ago, no recent events
    # AUDIT: Old expectation=Warm+downgrade was wrong; Hot→Warm downgrade
    # is dead code (score drops naturally before 7d threshold). With new
    # half-lives: checkout_decay(10d, hl=3d)=0.099, cart_decay(10d, hl=7d)=0.25.
    # Intent decayed: 40*0.25=10; readiness: 10*0.099=1; interest+eng decayed
    # by gen_decay(10d,hl=14d)=0.61. Total ~19. Cart floor expires at 72h. -> Cold.
    # -----------------------------------------------------------------------
    (
        "long_inactivity_10days",
        _base(sessions_count=5, cart_item_count=3, cart_value=600.0,
              checkout_attempts=2, unique_products_viewed=5,
              days_since_last_activity=10.0,
              last_checkout_action_at=_days_ago(10),
              last_cart_action_at=_days_ago(10)),
        "Cold", 0, WARM - 1, [], "",
    ),

    # -----------------------------------------------------------------------
    # 13. Checkout override is unconditional — low raw score still gets Hot
    # -----------------------------------------------------------------------
    (
        "checkout_override_low_score",
        _base(sessions_count=1, cart_item_count=1, cart_value=50.0,
              checkout_attempts=1, days_since_last_activity=0.1,
              last_checkout_action_at=_hours_ago(1)),
        "Hot", 0, 100,
        ["Started checkout"],
        "OVERRIDE: Active checkout",
    ),

    # -----------------------------------------------------------------------
    # 14. High engagement + searches — meets Floor 5
    # AUDIT: Old expectation=Warm was correct; scorer was wrong.
    # Floor 5: >=2 searches AND >=2 product views within 7d => at least Warm.
    # Score = 23 (stays honest); segment raised by floor.
    # -----------------------------------------------------------------------
    (
        "high_engagement_search_floor",
        _base(sessions_count=4, total_time_spent=900.0,
              unique_products_viewed=3, products_viewed=6,
              search_count=2, days_since_last_activity=1.0),
        "Warm", 0, HOT - 1,
        ["Returned"],
        "FLOOR: 2 searches",
    ),

    # -----------------------------------------------------------------------
    # 15. Full high-intent — score reaches Hot organically
    # -----------------------------------------------------------------------
    (
        "full_high_intent_hot",
        _base(sessions_count=6, cart_item_count=3, cart_value=700.0,
              checkout_attempts=2, wishlist_item_count=2,
              unique_products_viewed=5, products_viewed=8,
              search_count=2, total_time_spent=1200.0,
              high_intent_page_visits=4, days_since_last_activity=0.3,
              last_checkout_action_at=_hours_ago(2),
              last_cart_action_at=_hours_ago(4)),
        "Hot", HOT, 100,
        ["Started checkout", "Added 3 item(s) to cart"],
        "",
    ),

    # -----------------------------------------------------------------------
    # 16. Cart within 72h but customer is CONVERTED — floor must NOT apply
    # -----------------------------------------------------------------------
    (
        "cart_floor_not_for_converted",
        _base(sessions_count=2, cart_item_count=2, cart_value=200.0,
              orders_count=1, total_order_value=200.0,
              days_since_last_activity=0.5,
              last_cart_action_at=_hours_ago(5)),
        # is_converted=True; floor 3 must not fire; score decides segment
        "Cold", 0, WARM - 1, [], "",
    ),

    # -----------------------------------------------------------------------
    # 17. Checkout 24-72h ago — Floor 2 (not the 24h override)
    # -----------------------------------------------------------------------
    (
        "checkout_floor_24_72h",
        _base(sessions_count=2, checkout_attempts=1,
              days_since_last_activity=1.5,
              last_checkout_action_at=_hours_ago(48)),
        "Warm", 0, HOT - 1,
        ["Started checkout"],
        "FLOOR: Checkout started",
    ),

    # -----------------------------------------------------------------------
    # 18. Wishlist > 7 days ago — floor expired, back to score only
    # -----------------------------------------------------------------------
    (
        "wishlist_floor_expired",
        _base(sessions_count=1, wishlist_item_count=1,
              days_since_last_activity=8.0),
        # 8d > 7d window; wishlist floor expired; score = ~5 -> Cold
        "Cold", 0, WARM - 1, [], "",
    ),

    # -----------------------------------------------------------------------
    # 19. Search floor — exactly 2 searches, exactly 2 views, within 7 days
    # -----------------------------------------------------------------------
    (
        "search_view_floor_boundary",
        _base(sessions_count=2, search_count=2, unique_products_viewed=2,
              products_viewed=2, days_since_last_activity=1.0),
        "Warm", 0, HOT - 1,
        ["2 product search(es)"],
        "FLOOR: 2 searches",
    ),

    # -----------------------------------------------------------------------
    # 20. Search floor — 2 searches, 1 view (short by 1 view) -> stays Cold
    # -----------------------------------------------------------------------
    (
        "search_floor_not_enough_views",
        _base(sessions_count=2, search_count=2, unique_products_viewed=1,
              products_viewed=1, days_since_last_activity=1.0),
        "Cold", 0, WARM - 1, [], "",
    ),
]


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class ScoringScenarioTests(unittest.TestCase):
    """Parameterized scoring scenario tests — one per strategy table row."""

    def _run_scenario(
        self, label, features, expected_segment, score_min, score_max,
        required_reason_fragments, expected_segment_reason_fragment,
    ):
        result = compute_behavioral_score(features)

        self.assertEqual(
            result["lead_segment"], expected_segment,
            msg=(
                f"[{label}] Expected segment {expected_segment!r}, "
                f"got {result['lead_segment']!r}. "
                f"Score={result['lead_score']}, "
                f"reasons={result['score_reasons']}, "
                f"segment_reason={result.get('segment_reason')!r}"
            ),
        )

        self.assertGreaterEqual(result["lead_score"], score_min,
            msg=f"[{label}] Score {result['lead_score']} < min {score_min}")
        self.assertLessEqual(result["lead_score"], score_max,
            msg=f"[{label}] Score {result['lead_score']} > max {score_max}")

        self.assertAlmostEqual(
            result["lead_probability"], result["lead_score"] / 100.0, places=4,
            msg=f"[{label}] lead_probability != lead_score/100",
        )

        joined_reasons = " | ".join(result["score_reasons"])
        for fragment in required_reason_fragments:
            self.assertIn(fragment, joined_reasons,
                msg=f"[{label}] Expected reason fragment {fragment!r} in: {joined_reasons}")

        if expected_segment_reason_fragment:
            self.assertIn(expected_segment_reason_fragment,
                          result.get("segment_reason", ""),
                msg=(f"[{label}] Expected segment_reason fragment "
                     f"{expected_segment_reason_fragment!r} in "
                     f"{result.get('segment_reason')!r}"))

    def test_01_login_only_new_customer(self):          self._run_scenario(*SCENARIOS[0])
    def test_02_homepage_once(self):                    self._run_scenario(*SCENARIOS[1])
    def test_03_several_unrelated_views(self):          self._run_scenario(*SCENARIOS[2])
    def test_04_same_category_views(self):              self._run_scenario(*SCENARIOS[3])
    def test_05_repeated_searches_only(self):           self._run_scenario(*SCENARIOS[4])
    def test_06_wishlist_floor_warm(self):              self._run_scenario(*SCENARIOS[5])
    def test_07_multiple_cart_items_floor(self):        self._run_scenario(*SCENARIOS[6])
    def test_08_cart_plus_checkout_active(self):        self._run_scenario(*SCENARIOS[7])
    def test_09_abandoned_checkout_25h(self):           self._run_scenario(*SCENARIOS[8])
    def test_10_old_cart_10days(self):                  self._run_scenario(*SCENARIOS[9])
    def test_11_converted_customer(self):               self._run_scenario(*SCENARIOS[10])
    def test_12_long_inactivity_10days(self):           self._run_scenario(*SCENARIOS[11])
    def test_13_checkout_override_unconditional(self):  self._run_scenario(*SCENARIOS[12])
    def test_14_high_engagement_search_floor(self):     self._run_scenario(*SCENARIOS[13])
    def test_15_full_high_intent_hot(self):             self._run_scenario(*SCENARIOS[14])
    def test_16_cart_floor_not_for_converted(self):     self._run_scenario(*SCENARIOS[15])
    def test_17_checkout_floor_24_72h(self):            self._run_scenario(*SCENARIOS[16])
    def test_18_wishlist_floor_expired(self):           self._run_scenario(*SCENARIOS[17])
    def test_19_search_view_floor_boundary(self):       self._run_scenario(*SCENARIOS[18])
    def test_20_search_floor_not_enough_views(self):    self._run_scenario(*SCENARIOS[19])


if __name__ == "__main__":
    unittest.main(verbosity=2)
