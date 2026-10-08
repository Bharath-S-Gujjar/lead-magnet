"""Controlled manual verification script for Real Gmail delivery (Step 4).

Usage:
    python test_price_drop_gmail.py
    python test_price_drop_gmail.py --recipient your.email@example.com --source wishlist

Safety Rules:
    - Never runs automatically during pytest or test suites.
    - Dispatches exactly ONE email per execution.
    - Uses existing configured Gmail SMTP credentials from backend/.env.
    - Never prints or reveals SMTP secrets or passwords.
    - Makes 0 ReefAPI calls.
    - Prints the communication ID, provider message ID, and provider result.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
import dotenv
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load backend/.env safely
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    dotenv.load_dotenv(env_path, override=True)
else:
    dotenv.load_dotenv()

from communication_provider import GmailSMTPProvider, _build_html_body
from opportunity_engine import OPP_PRODUCT_PRICE_DROP, build_opportunity_email_content
import app as app_module


def send_single_real_price_drop_email(recipient_email, interest_source="cart"):
    """Dispatch exactly ONE real product_price_drop email via Gmail SMTP."""
    print("=" * 65)
    print("STEP 4: CONTROLLED MANUAL REAL GMAIL DELIVERY TEST")
    print("=" * 65)

    # 1. Check SMTP Credentials
    smtp_user = os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM_EMAIL") or os.getenv("GMAIL_FROM_EMAIL") or smtp_user
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.getenv("SMTP_PORT", "587")

    print("\n[1] Verifying Gmail SMTP Configuration:")
    print(f"    Host:      {smtp_host}:{smtp_port}")
    print(f"    Username:  {'CONFIGURED' if smtp_user else 'MISSING'}")
    print(f"    Password:  {'CONFIGURED' if smtp_pass else 'MISSING'}")
    print(f"    From:      {'CONFIGURED' if smtp_from else 'MISSING'}")

    if not (smtp_user and smtp_pass and smtp_from):
        print("\n[ERROR] Gmail SMTP credentials are not fully configured in backend/.env.")
        print("Required: SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL")
        sys.exit(1)

    print(f"\n[2] Target Test Recipient:")
    print(f"    Email:     {recipient_email}")
    print(f"    Source:    {interest_source.upper()}")

    # 2. Existing Myntra Product sample (Zero ReefAPI calls)
    test_opportunity = {
        "_id": ObjectId(),
        "customer_id": ObjectId(),
        "opportunity_type": OPP_PRODUCT_PRICE_DROP,
        "opportunity_key": f"opp:test:price_drop:28420390:999_599",
        "product_id": "myntra_28420390",
        "product_name": "Roadster Men Solid Casual Shirt",
        "opportunity_state": "detected",
        "metadata": {
            "product_id": "myntra_28420390",
            "source_product_id": "28420390",
            "product_title": "Roadster Men Solid Casual Shirt",
            "product_name": "Roadster Men Solid Casual Shirt",
            "brand": "Roadster",
            "old_price": 999,
            "new_price": 599,
            "discount_amount": 400,
            "discount_percentage": 40,
            "primary_image": "https://assets.myntassets.com/h_720,q_90/v1/assets/images/28420390/2024/2/23/roadster_shirt.jpg",
            "product_url": "https://www.myntra.com/shirts/roadster/roadster-men-solid-casual-shirt/28420390/buy",
            "interest_source": interest_source,
            "source": "myntra",
        },
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }

    # 3. Build customer-facing email content
    subject, body = build_opportunity_email_content(
        test_opportunity, customer_name="Valued Customer", store_url="http://localhost:3001"
    )

    print("\n[3] Prepared Customer-Facing Email Content:")
    print(f"    Subject:   {subject}")
    print("    --- Body Preview ---")
    for line in body.split("\n"):
        print(f"    {line}")
    print("    --------------------")

    # 4. Dispatch exactly ONE email using GmailSMTPProvider
    print("\n[4] Dispatching via GmailSMTPProvider...")
    provider = GmailSMTPProvider()
    meta = test_opportunity["metadata"]

    res = provider.send_email(
        recipient=recipient_email,
        subject=subject,
        body=body,
        metadata=meta,
    )

    print("\n[5] Delivery Result:")
    print(f"    Success:             {res.get('success')}")
    print(f"    Provider:            {res.get('provider')}")
    print(f"    Provider Message-ID: {res.get('provider_message_id')}")
    if not res.get("success"):
        print(f"    Error:               {res.get('error')}")

    # 5. Log communication if DB available
    db = getattr(app_module, "db", None)
    comm_id = None
    if db is not None:
        try:
            comm_doc = {
                "customer_id": test_opportunity["customer_id"],
                "campaign_type": "product_price_drop",
                "channel": "email",
                "status": "sent" if res.get("success") else "failed",
                "provider": res.get("provider"),
                "provider_message_id": res.get("provider_message_id"),
                "recipient": recipient_email,
                "subject": subject,
                "body": body,
                "metadata": meta,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "sent_at": datetime.now(timezone.utc).isoformat() if res.get("success") else None,
            }
            ins_res = db["marketing_communications"].insert_one(comm_doc)
            comm_id = str(ins_res.inserted_id)
            print(f"    Communication ID:    {comm_id}")
        except Exception as e:
            print(f"    (Database logging skipped: {e})")
    else:
        print("    Communication ID:    (db not connected - standalone run)")

    print("\n" + "=" * 65)
    if res.get("success"):
        print("SUCCESS: Exactly ONE real price-drop email was relayed to Gmail MTA.")
        print(f"Target inbox: {recipient_email}")
        print("Check Inbox / Spam / Promotions folder for confirmation.")
    else:
        print("DELIVERY FAILED: See error details above.")
    print("=" * 65)
    return res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual verification test for real Gmail delivery")
    default_recipient = os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER") or "gustavofringe942@gmail.com"
    parser.add_argument("--recipient", default=default_recipient, help=f"Destination email (default: {default_recipient})")
    parser.add_argument("--source", choices=["cart", "wishlist"], default="cart", help="Interest source (cart or wishlist)")
    args = parser.parse_args()

    send_single_real_price_drop_email(recipient_email=args.recipient, interest_source=args.source)
