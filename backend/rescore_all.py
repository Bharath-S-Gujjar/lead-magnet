"""Legacy Customer Rescoring Script - DEPRECATED.

.. deprecated:: Phase-5
   Use the safe, audited rescoring CLI instead:
     python scripts/rescore_customers.py          # Dry-run
     python scripts/rescore_customers.py --apply  # Apply to local DB
"""

import sys

def main():
    print("=" * 70)
    print("DEPRECATION NOTICE: backend/rescore_all.py has been retired.")
    print("=" * 70)
    print("Please use the safe, audited rescoring CLI:")
    print("  python scripts/rescore_customers.py                  (dry-run)")
    print("  python scripts/rescore_customers.py --apply          (apply changes)")
    print("=" * 70)
    sys.exit(0)

if __name__ == "__main__":
    main()

