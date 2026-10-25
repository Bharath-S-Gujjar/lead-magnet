"""Lead Magnet: Authoritative Scoring Constants
================================================

Single source of truth for all segment thresholds, override windows, and
scoring-related configuration.  Every service that needs these values MUST
import them from here; no module may hard-code 0.65 / 0.70 / 0.35 / 0.30
probability literals or duplicate threshold integers.

Segment thresholds (100-point behavioral scale):
    Hot:  score >= HOT   -> high intent, engage immediately
    Warm: score >= WARM  -> meaningful interest, nurture
    Cold: score  < WARM  -> low / unproven intent

Override windows:
    CHECKOUT_OVERRIDE_HOURS: active checkout within this window forces Hot
        segment regardless of total score (score itself remains honest).
"""

# -- Segment Thresholds (integer points, 0-100 scale) -------------------------
HOT: int = 70
WARM: int = 35

# -- Override & Floor Windows -------------------------------------------------
CHECKOUT_OVERRIDE_HOURS: int = 24      # active-checkout -> Hot segment override
CHECKOUT_WARM_FLOOR_HOURS: int = 72    # checkout within 72h -> at least Warm
CART_WARM_FLOOR_HOURS: int = 72        # cart add/update within 72h -> at least Warm
WISHLIST_WARM_FLOOR_DAYS: int = 7     # wishlist add within 7 days -> at least Warm
# Note: Hot->Warm 7-day inactivity downgrade rule was removed as dead code:
# under half-lives (checkout=3d, cart=7d, general=14d), maximum possible score
# at >=7 days of inactivity is ~48 (< 70), so a customer's score naturally decays
# below Hot without an artificial downgrade rule.

# -- Recency Decay Half-Lives (days) -----------------------------------------
# Calibrated so that a customer who was Hot stays Warm for ~7 days after going
# cold, and doesn't fully decay to Cold for ~14 days.
HALFLIFE_CHECKOUT_DAYS: int = 3   # checkout signal decays over ~3 days
HALFLIFE_CART_DAYS: int = 7       # cart signal decays over ~7 days
HALFLIFE_GENERAL_DAYS: int = 14   # browsing/engagement decays over ~14 days

# -- Derived probability equivalents (score / 100, for documentation only) ----
# These are NOT calibrated probabilities; they are score fractions and must
# never be used as ML probability thresholds in isolation.
HOT_PROBABILITY_EQUIV: float = HOT / 100.0    # 0.70
WARM_PROBABILITY_EQUIV: float = WARM / 100.0  # 0.35
