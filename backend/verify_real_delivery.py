"""Controlled verification harness for Real Gmail and WhatsApp delivery (Phase 4).

Usage:
    python verify_real_delivery.py --check-config
    python verify_real_delivery.py --send-email <recipient_email>
    python verify_real_delivery.py --send-whatsapp <recipient_phone>
    python verify_real_delivery.py --test-both <recipient_email> <recipient_phone>

Safety Rules:
    - Never prints or logs secrets/tokens/passwords.
    - Operates only on explicitly provided test recipient.
    - Cleans up created test records in MongoDB Atlas where applicable.
    - Does not alter catalog or admin documents.

IMPORTANT -- What 'success=True' means:
    success=True means the Gmail SMTP server accepted the message for queuing.
    It does NOT mean the recipient received the email.
    Always verify delivery by checking:
      1. Sender's Gmail Sent folder (confirm message was accepted)
      2. Recipient's Spam / Promotions / All Mail folders
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

from communication_provider import (
    GmailSMTPProvider,
    WhatsAppBusinessProvider,
    MultiChannelProvider,
)
from marketing_automation_service import (
    trigger_registration_communication,
    get_store_url,
)
import app as app_module


def check_configuration():
    """Report credential configuration status without revealing secrets."""
    print("=" * 60)
    print("PHASE 4: REAL DELIVERY CREDENTIALS STATUS")
    print("=" * 60)

    # 1. Gmail SMTP Configuration
    smtp_user = os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM_EMAIL") or os.getenv("GMAIL_FROM_EMAIL") or smtp_user
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.getenv("SMTP_PORT", "587")

    print("\n[Gmail SMTP Configuration]")
    print(f"  SMTP_HOST:        {smtp_host}")
    print(f"  SMTP_PORT:        {smtp_port}")
    print(f"  SMTP_USERNAME:    {'CONFIGURED' if smtp_user else 'MISSING'}")
    print(f"  SMTP_PASSWORD:    {'CONFIGURED' if smtp_pass else 'MISSING'}")
    print(f"  SMTP_FROM_EMAIL:   {'CONFIGURED' if smtp_from else 'MISSING'}")

    gmail_ready = bool(smtp_user and smtp_pass and smtp_from)
    print(f"  --> Gmail Ready:   {'YES' if gmail_ready else 'NO (credentials missing)'}")

    # 2. WhatsApp Business Configuration
    wa_token = os.getenv("WHATSAPP_API_TOKEN") or os.getenv("META_WHATSAPP_TOKEN")
    wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("META_PHONE_NUMBER_ID")
    wa_url = os.getenv("WHATSAPP_API_URL") or f"https://graph.facebook.com/{os.getenv('WHATSAPP_GRAPH_VERSION', 'v18.0')}"

    print("\n[WhatsApp Business / Meta Cloud API Configuration]")
    print(f"  API_URL:                  {wa_url}")
    print(f"  WHATSAPP_API_TOKEN:       {'CONFIGURED' if wa_token else 'MISSING'}")
    print(f"  WHATSAPP_PHONE_NUMBER_ID: {'CONFIGURED' if wa_phone_id else 'MISSING'}")

    wa_ready = bool(wa_token and wa_phone_id)
    print(f"  --> WhatsApp Ready:       {'YES' if wa_ready else 'NO (credentials missing)'}")

    # 3. Storefront URL
    store_url = get_store_url()
    print("\n[Storefront URL Configuration]")
    print(f"  Resolved Store URL:       {store_url}")
    print(f"  Controlling Env Var:      {'STORE_URL' if os.getenv('STORE_URL') else ('FRONTEND_USER_URL' if os.getenv('FRONTEND_USER_URL') else ('FRONTEND_URL' if os.getenv('FRONTEND_URL') else 'DEFAULT (localhost:3001)'))}")

    print("=" * 60)
    return gmail_ready, wa_ready


def run_controlled_email_test(recipient_email):
    """Dispatch a single controlled test email via real Gmail SMTP."""
    gmail_ready, _ = check_configuration()
    if not gmail_ready:
        print("\nERROR: Cannot run real email delivery test — Gmail SMTP credentials are missing from backend/.env")
        return False

    print(f"\nTriggering controlled real email test to: {recipient_email}")
    provider = GmailSMTPProvider()
    subject = "Lead Magnet — Real Delivery Verification"
    body = (
        "Hi,\n\n"
        "This is a verified test email from the Lead Magnet Communication Engine (Phase 4).\n"
        "All customer communication business rules and store links are active.\n\n"
        f"Store Link: {get_store_url()}\n\n"
        "Best regards,\n"
        "The Lead Magnet Team"
    )

    result = provider.send_email(recipient_email, subject, body)
    print(f"Result: {result}")
    smtp_accepted = result.get("success", False)
    if smtp_accepted:
        print("[SMTP ACCEPTED] Gmail SMTP server accepted the message for queuing.")
        print("  provider_message_id is the RFC 2822 Message-ID assigned by this application.")
        print("  This confirms SMTP acceptance -- NOT inbox delivery.")
        print("  Next steps:")
        print("    1. Open sender Gmail account -> Check 'Sent' folder")
        print("    2. Open recipient inbox -> Check Spam / Promotions / All Mail")
        print(f"    3. Search recipient inbox for: subject:\"Lead Magnet\"")
    else:
        print("[SMTP FAILED] Gmail SMTP rejected the message. See error above.")
    return smtp_accepted


def run_controlled_whatsapp_test(recipient_phone):
    """Dispatch a single controlled test WhatsApp message via Meta Cloud API."""
    _, wa_ready = check_configuration()
    if not wa_ready:
        print("\nERROR: Cannot run real WhatsApp delivery test — WhatsApp Business credentials are missing from backend/.env")
        return False

    print(f"\nTriggering controlled real WhatsApp test to: {recipient_phone}")
    provider = WhatsAppBusinessProvider()
    body = f"Hi 👋 This is a verified test message from Lead Magnet (Phase 4). Store: {get_store_url()}"

    result = provider.send_whatsapp(recipient_phone, body)
    print(f"Result: {result}")
    return result.get("success", False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify real communication delivery")
    parser.add_argument("--check-config", action="store_true", help="Check credentials configuration")
    parser.add_argument("--send-email", type=str, help="Recipient email address for controlled test")
    parser.add_argument("--send-whatsapp", type=str, help="Recipient phone number for controlled test")
    args = parser.parse_args()

    if args.send_email:
        run_controlled_email_test(args.send_email)
    elif args.send_whatsapp:
        run_controlled_whatsapp_test(args.send_whatsapp)
    else:
        check_configuration()
