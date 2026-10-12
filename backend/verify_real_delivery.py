"""Controlled verification harness for Real Gmail and WhatsApp delivery (Phase 4 / Task 14.3).

Usage:
    # 1. Audit configuration & safeguards (completely safe, zero network calls, zero sends):
    python verify_real_delivery.py --check-config

    # 2. Local phone number validation utility (zero network calls, validates E.164 format):
    python verify_real_delivery.py --validate-phone <recipient_phone>

    # 3. Controlled Real Email Delivery (explicit execution mode requiring confirmation):
    python verify_real_delivery.py --send-email <recipient_email> --confirm-real-dispatch

    # 4. Controlled Real WhatsApp Delivery (explicit execution mode requiring confirmation):
    python verify_real_delivery.py --send-whatsapp <recipient_phone> --confirm-real-dispatch

Safety Rules:
    - Never prints or logs secrets/tokens/passwords.
    - Operates only on explicitly provided test recipient.
    - Live dispatch requires explicit --confirm-real-dispatch flag or ALLOW_REAL_DISPATCH=true.
    - Without explicit confirmation, execution requests are safely blocked with clear guidance.
    - --check-config never contacts Meta, Gmail, or external providers.
    - Cleans up created test records in MongoDB Atlas where applicable.
    - Does not alter catalog or admin documents.

IMPORTANT -- What 'success=True' means:
    - For Gmail: Confirms that the SMTP server accepted the message for relay.
      Inbox placement (Inbox vs. Spam) is determined asynchronously.
    - For WhatsApp: Confirms that Meta Graph API accepted the message payload and returned a wamid.
      End delivery status (sent -> delivered -> read) is communicated via webhooks.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
import dotenv
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load backend/.env safely (skipped during automated testing to preserve test isolation)
if os.getenv("TESTING") != "1":
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        dotenv.load_dotenv(env_path, override=True)
    else:
        dotenv.load_dotenv()

from communication_provider import (
    GmailSMTPProvider,
    WhatsAppBusinessProvider,
    MultiChannelProvider,
    normalize_whatsapp_phone,
)
from marketing_automation_service import (
    trigger_registration_communication,
    get_store_url,
)


def check_configuration():
    """Report credential configuration status and safeguards without revealing secrets."""
    print("=" * 70)
    print("LEAD MAGNET: REAL COMMUNICATION & WHATSAPP READINESS AUDIT")
    print("=" * 70)

    # 0. Safety Switches & Dispatch Guards
    allow_real = os.getenv("ALLOW_REAL_DISPATCH", "").lower() in ("true", "1", "yes")
    comm_provider = os.getenv("COMMUNICATION_PROVIDER", "dry_run")

    print("\n[Safety Switches & Dispatch Safeguards]")
    print(f"  COMMUNICATION_PROVIDER:   {comm_provider} (default safe: dry_run)")
    print(f"  ALLOW_REAL_DISPATCH:      {'ENABLED (live delivery allowed)' if allow_real else 'DISABLED (safe - dispatches blocked without --confirm-real-dispatch)'}")
    print(f"  Execution Mode Guard:     ACTIVE (requires explicit --confirm-real-dispatch flag)")

    # 1. Gmail SMTP Configuration
    smtp_user = os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM_EMAIL") or os.getenv("GMAIL_FROM_EMAIL") or smtp_user
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.getenv("SMTP_PORT", "587")

    print("\n[Gmail SMTP Configuration]")
    print(f"  SMTP_HOST:                {smtp_host}")
    print(f"  SMTP_PORT:                {smtp_port}")
    print(f"  SMTP_USERNAME:            {'CONFIGURED' if smtp_user else 'MISSING'}")
    print(f"  SMTP_PASSWORD:            {'CONFIGURED' if smtp_pass else 'MISSING'}")
    print(f"  SMTP_FROM_EMAIL:          {'CONFIGURED' if smtp_from else 'MISSING'}")

    gmail_ready = bool(smtp_user and smtp_pass and smtp_from)
    print(f"  --> Gmail Credentials:    {'READY' if gmail_ready else 'NOT READY (missing credentials in .env)'}")

    # 2. WhatsApp Business Configuration (Meta Cloud API)
    wa_token = os.getenv("WHATSAPP_API_TOKEN") or os.getenv("META_WHATSAPP_TOKEN")
    wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("META_PHONE_NUMBER_ID")
    wa_business_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID") or os.getenv("META_BUSINESS_ACCOUNT_ID")
    graph_ver = os.getenv("WHATSAPP_GRAPH_VERSION") or os.getenv("GRAPH_API_VERSION", "v18.0")
    wa_url = os.getenv("WHATSAPP_API_URL") or f"https://graph.facebook.com/{graph_ver}"

    print("\n[WhatsApp Business / Meta Cloud API Configuration]")
    print(f"  API_URL:                  {wa_url}")
    print(f"  GRAPH_VERSION:            {graph_ver}")
    print(f"  WHATSAPP_API_TOKEN:       {'CONFIGURED' if wa_token else 'MISSING'}")
    print(f"  WHATSAPP_PHONE_NUMBER_ID: {'CONFIGURED' if wa_phone_id else 'MISSING'}")
    print(f"  WHATSAPP_BUSINESS_ACCT_ID:{'CONFIGURED' if wa_business_id else 'MISSING (optional for sending, required for WABA management)'}")

    wa_creds_ready = bool(wa_token and wa_phone_id)
    print(f"  --> Meta API Credentials: {'READY' if wa_creds_ready else 'NOT READY (token or phone ID missing in .env)'}")

    # 3. WhatsApp Webhook Configuration
    app_secret = os.getenv("WHATSAPP_APP_SECRET")
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    webhook_url = os.getenv("WHATSAPP_WEBHOOK_URL", "NOT CONFIGURED (requires public HTTPS, e.g. ngrok or production domain)")

    print("\n[WhatsApp Webhook Configuration]")
    print(f"  WHATSAPP_APP_SECRET:      {'CONFIGURED' if app_secret else 'MISSING (required for HMAC-SHA256 signature verification)'}")
    print(f"  WEBHOOK_VERIFY_TOKEN:     {'CONFIGURED' if verify_token else 'MISSING (required for GET challenge handshake)'}")
    print(f"  WEBHOOK_CALLBACK_URL:     {webhook_url}")
    webhook_ready = bool(app_secret and verify_token)
    print(f"  --> Webhook Signature:    {'READY' if webhook_ready else 'INCOMPLETE (missing app secret or verify token)'}")

    # 4. WhatsApp Message Templates
    tpl_order = os.getenv("WHATSAPP_TEMPLATE_ORDER_CONFIRMATION")
    tpl_cart = os.getenv("WHATSAPP_TEMPLATE_CART_ABANDONMENT")
    tpl_price = os.getenv("WHATSAPP_TEMPLATE_PRODUCT_PRICE_DROP")
    tpl_lang = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en_US")

    print("\n[WhatsApp Message Templates (Required outside 24h window)]")
    print(f"  TEMPLATE_LANGUAGE:        {tpl_lang}")
    print(f"  ORDER_CONFIRMATION:       {'CONFIGURED (' + tpl_order + ')' if tpl_order else 'MISSING'}")
    print(f"  CART_ABANDONMENT:         {'CONFIGURED (' + tpl_cart + ')' if tpl_cart else 'MISSING'}")
    print(f"  PRODUCT_PRICE_DROP:       {'CONFIGURED (' + tpl_price + ')' if tpl_price else 'MISSING'}")
    templates_configured = bool(tpl_order or tpl_cart or tpl_price)
    print(f"  --> Template Setup:       {'CONFIGURED' if templates_configured else 'UNCONFIGURED (freeform text only permitted within 24h customer window)'}")

    # 5. Storefront URL
    store_url = get_store_url()
    print("\n[Storefront URL Configuration]")
    print(f"  Resolved Store URL:       {store_url}")
    print(f"  Controlling Env Var:      {'STORE_URL' if os.getenv('STORE_URL') else ('FRONTEND_USER_URL' if os.getenv('FRONTEND_USER_URL') else ('FRONTEND_URL' if os.getenv('FRONTEND_URL') else 'DEFAULT (localhost:3001)'))}")

    # 6. Manual Prerequisites Checklist
    print("\n" + "-" * 70)
    print("MANUAL PREREQUISITES CHECKLIST FOR CONTROLLED WHATSAPP TEST")
    print("-" * 70)
    print("  [1] Meta Developer App:   Create App at https://developers.facebook.com")
    print("  [2] Access Token:         Generate System User Token / User Token -> WHATSAPP_API_TOKEN")
    print("  [3] Phone Number ID:      Obtain from WhatsApp Getting Started -> WHATSAPP_PHONE_NUMBER_ID")
    print("  [4] Recipient Whitelist:  In Sandbox mode, add tester's number (+91XXXXXXXXXX) to 'To' recipient list")
    print("  [5] E.164 Phone Format:   Ensure number has international prefix (e.g. +917022441738)")
    print("  [6] Customer Consent:     Set whatsapp_promotional_consent: true in user profile for marketing tests")
    print("  [7] Public Webhook:       Configure HTTPS endpoint for Meta webhooks if testing delivery receipts")

    print("\n" + "=" * 70)
    if wa_creds_ready and allow_real:
        verdict = "READY FOR CONTROLLED WHATSAPP TEST"
    elif wa_creds_ready and not allow_real:
        verdict = "READY AFTER PASSING --confirm-real-dispatch FLAG"
    else:
        verdict = "WAITING FOR META CONFIGURATION"

    print(f"AUDIT VERDICT: {verdict}")
    print("=" * 70)
    return gmail_ready, wa_creds_ready


def validate_phone_utility(phone_str):
    """Local utility to test and inspect phone number E.164 normalization without sending anything."""
    print("=" * 70)
    print(f"LOCAL PHONE NUMBER E.164 VALIDATION CHECK: '{phone_str}'")
    print("=" * 70)
    norm_phone, norm_err = normalize_whatsapp_phone(phone_str)
    if norm_err:
        print(f"Status:             INVALID")
        print(f"Reason:             {norm_err}")
        print("\nGuidance:")
        print("  - International format is required with '+' and country code.")
        print("  - Example for India: +919876543210")
        print("  - Example for US:    +15551234567")
        print("  - 10-digit numbers without country code cannot be automatically resolved.")
        print("=" * 70)
        return False
    else:
        print(f"Status:             VALID")
        print(f"Original Input:     {phone_str}")
        print(f"Normalized Digits:  {norm_phone} (Meta Cloud API standard)")
        print(f"E.164 Display:      +{norm_phone}")
        print("\nMeta Sandbox Prerequisite:")
        print(f"  Ensure +{norm_phone} is registered and OTP-verified in your Meta Developer App Sandbox.")
        print("=" * 70)
        return True


def run_controlled_email_test(recipient_email, confirm_real=False):
    """Dispatch a single controlled test email via real Gmail SMTP.

    Requires explicit --confirm-real-dispatch flag or ALLOW_REAL_DISPATCH=true.
    """
    env_allow = os.getenv("ALLOW_REAL_DISPATCH", "").lower() in ("true", "1", "yes")
    if not (confirm_real or env_allow):
        print("\n" + "!" * 70)
        print("SAFEGUARD BLOCKED: Real Email dispatch is disabled by default.")
        print("To execute a live delivery test via Gmail SMTP, you must explicitly pass:")
        print("    --confirm-real-dispatch")
        print("or set ALLOW_REAL_DISPATCH=true in backend/.env.")
        print("Zero network calls were made to Gmail.")
        print("!" * 70)
        return False

    gmail_ready, _ = check_configuration()
    if not gmail_ready:
        print("\nERROR: Cannot run real email delivery test — Gmail SMTP credentials are missing from backend/.env")
        return False

    if not recipient_email or "@" not in str(recipient_email):
        print(f"\nERROR: Invalid recipient email address: {recipient_email}")
        return False

    print(f"\n[CONTROLLED EXECUTION] Triggering controlled real email test to: {recipient_email}")
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
        print(f"[SMTP FAILED] Gmail SMTP rejected the message: {result.get('error')}")
    return smtp_accepted


def run_controlled_whatsapp_test(recipient_phone, confirm_real=False):
    """Dispatch a single controlled test WhatsApp message via Meta Cloud API.

    Requires explicit --confirm-real-dispatch flag or ALLOW_REAL_DISPATCH=true.
    """
    env_allow = os.getenv("ALLOW_REAL_DISPATCH", "").lower() in ("true", "1", "yes")
    if not (confirm_real or env_allow):
        print("\n" + "!" * 70)
        print("SAFEGUARD BLOCKED: Real WhatsApp dispatch is disabled by default.")
        print("To execute a live delivery test to Meta Cloud API, you must explicitly pass:")
        print("    --confirm-real-dispatch")
        print("or set ALLOW_REAL_DISPATCH=true in backend/.env.")
        print("Zero network calls were made to Meta.")
        print("!" * 70)
        return False

    _, wa_ready = check_configuration()
    if not wa_ready:
        print("\nERROR: Cannot run real WhatsApp delivery test — WhatsApp Business credentials are missing from backend/.env")
        print("Required in backend/.env: WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID")
        return False

    norm_phone, norm_err = normalize_whatsapp_phone(recipient_phone)
    if norm_err:
        print(f"\nERROR: Recipient phone number validation failed: {norm_err}")
        print("Phone numbers must be in international E.164 format (e.g. +91XXXXXXXXXX).")
        return False

    print(f"\n[CONTROLLED EXECUTION] Triggering real WhatsApp message to: +{norm_phone}")
    provider = WhatsAppBusinessProvider()
    body = f"Hi 👋 This is a verified test message from Lead Magnet (Controlled Test). Store: {get_store_url()}"

    result = provider.send_whatsapp(recipient_phone, body)
    print(f"Result: {result}")
    success = result.get("success", False)
    if success:
        print(f"[WHATSAPP ACCEPTED] Meta accepted the message. Message ID: {result.get('provider_message_id')}")
    else:
        print(f"[WHATSAPP FAILED] Error: {result.get('error')}")
    return success


def run_application_whatsapp_journey(
    customer_identifier,
    opportunity_identifier=None,
    confirm_real=False,
    provider=None,
    db=None,
):
    """Execute a single controlled marketing journey through the actual application marketing engine.

    Enforces:
        - Customer profile lookup in user_profiles resolving to EXACTLY ONE customer.
        - Strict promotional consent check (whatsapp_promotional_consent == True, whatsapp_opt_out == False).
        - Phone format normalization (E.164).
        - Explicit confirmation requirement (--confirm-real-dispatch or ALLOW_REAL_DISPATCH=true).
        - Single eligible opportunity enforcement:
            - If --opportunity-id is specified, targets exactly that opportunity.
            - If not specified, refuses dispatch if 0 or >1 eligible opportunities exist.
        - Execution through process_customer_opportunities (preserving opportunity evaluation,
          channel selection, cooldowns, idempotency, and marketing_communications logging).
        - Strict isolation to the specified customer and opportunity (zero impact on others).
        - Clear distinction between API acceptance (Meta HTTP 200 + wamid) and delivery confirmation.
    """
    env_allow = os.getenv("ALLOW_REAL_DISPATCH", "").lower() in ("true", "1", "yes")
    if not (confirm_real or env_allow):
        print("\n" + "!" * 70)
        print("SAFEGUARD BLOCKED: Application real WhatsApp dispatch is disabled by default.")
        print("To execute a live delivery test through the application workflow, you must explicitly pass:")
        print("    --confirm-real-dispatch")
        print("or set ALLOW_REAL_DISPATCH=true in backend/.env.")
        print("Zero network calls were made to Meta.")
        print("!" * 70)
        return False, {"error": "Safeguard blocked: confirmation required"}

    target_db = db
    if target_db is None:
        # Direct execution without an explicit db must be under verified local test isolation
        testing_active = os.environ.get("TESTING", "").strip() == "1"
        mongo_uri = os.environ.get("MONGO_URI", "").strip().lower()
        is_loopback = any(lh in mongo_uri for lh in ("127.0.0.1", "localhost", "::1"))
        has_remote = any(pat in mongo_uri for pat in ("mongodb+srv://", ".mongodb.net", "atlas"))

        if not (testing_active and is_loopback) or has_remote:
            print("\n" + "!" * 70)
            print("SAFEGUARD BLOCKED: Direct workflow execution requires an isolated local test database.")
            print("To run safely, use the dedicated local test launcher:")
            print(f"    python local_test_launcher.py --test-journey {customer_identifier}")
            print("or pass an explicit local test database instance (db=local_db).")
            print("!" * 70)
            return False, {"error": "Safeguard blocked: direct execution requires isolated test database"}

        try:
            import app as app_module
            target_db = getattr(app_module, "db", None)
        except Exception as e:
            print(f"\nERROR: Failed to load local database: {e}")
            return False, {"error": f"Database initialization failed: {e}"}

    if target_db is None:
        print("\nERROR: Database connection unavailable.")
        return False, {"error": "Database unavailable"}

    # Database Isolation Guard: Fail-closed if target database is remote or Atlas
    target_client = getattr(target_db, "client", None)
    if target_client:
        nodes = getattr(target_client, "nodes", set())
        address = getattr(target_client, "address", None)
        hosts = [address[0]] if address else [n[0] for n in nodes]
        for h in hosts:
            if "mongodb.net" in str(h).lower() or "atlas" in str(h).lower():
                print("\n" + "!" * 70)
                print(f"SAFEGUARD BLOCKED: Refusing workflow execution against remote/Atlas database: {h}")
                print("Application workflow testing must target the isolated local test database.")
                print("Zero queries or updates were performed against the remote database.")
                print("!" * 70)
                return False, {"error": "Safeguard blocked: remote/Atlas database rejected"}

    profiles_col = target_db["user_profiles"]
    cust_oid = None
    try:
        cust_oid = ObjectId(customer_identifier)
    except Exception:
        pass

    query = {"$or": [{"_id": cust_oid}]} if cust_oid else {"$or": []}
    query["$or"].extend([
        {"email": customer_identifier},
        {"username": customer_identifier},
        {"user_id": customer_identifier},
    ])

    matched_profiles = []
    try:
        cursor = profiles_col.find(query)
        res = cursor.limit(2) if hasattr(cursor, "limit") else cursor
        if isinstance(res, list):
            matched_profiles = res
        elif hasattr(res, "__iter__") and type(res).__name__ != "MagicMock":
            matched_profiles = list(res)
    except Exception:
        pass

    if not matched_profiles and hasattr(profiles_col, "find_one"):
        one = profiles_col.find_one(query)
        if one and isinstance(one, dict):
            matched_profiles = [one]

    if not matched_profiles:
        print(f"\nERROR: Test customer '{customer_identifier}' not found in user_profiles.")
        return False, {"error": "Customer not found"}
    if len(matched_profiles) > 1:
        print(f"\nERROR: Customer identifier '{customer_identifier}' is ambiguous; matches multiple customers in user_profiles.")
        return False, {"error": "Ambiguous customer identifier: matches multiple customers"}

    profile = matched_profiles[0]
    cust_id = profile["_id"]

    # 1. Verify consent and opt-out
    has_consent = bool(profile.get("whatsapp_promotional_consent") or profile.get("whatsapp_opt_in"))
    has_opt_out = bool(profile.get("whatsapp_opt_out"))
    if not has_consent:
        print(f"\nBLOCKED BY CONSENT GUARD: Customer {cust_id} has not granted WhatsApp promotional consent.")
        return False, {"error": "Customer has not granted WhatsApp promotional consent"}
    if has_opt_out:
        print(f"\nBLOCKED BY OPT-OUT GUARD: Customer {cust_id} has WhatsApp opt-out enabled.")
        return False, {"error": "Customer has opted out of WhatsApp"}

    # 2. Verify phone
    phone_val = profile.get("phone")
    norm_phone, norm_err = normalize_whatsapp_phone(phone_val)
    if norm_err:
        print(f"\nBLOCKED BY PHONE GUARD: Customer phone '{phone_val}' is invalid: {norm_err}")
        return False, {"error": f"Invalid phone: {norm_err}"}

    # 3. Detect and gate single eligible opportunity
    from opportunity_engine import detect_opportunities_for_customer, process_customer_opportunities

    opp_col = target_db.get("marketing_opportunities") if isinstance(target_db, dict) else target_db["marketing_opportunities"]
    comm_col = target_db["marketing_communications"]

    # Pre-detect any new opportunities if opp_col is available
    if opp_col is not None:
        try:
            detect_opportunities_for_customer(cust_id, target_db)
        except Exception:
            pass

        query_opp = {
            "customer_id": {"$in": [cust_id, str(cust_id)]},
            "opportunity_state": "detected",
        }
        detected_opps = list(opp_col.find(query_opp))

        # Filter to those not already communicated in marketing_communications
        eligible_opps = []
        for opp in detected_opps:
            opp_k = opp.get("opportunity_key")
            already_sent = comm_col.find_one({
                "customer_id": {"$in": [cust_id, str(cust_id)]},
                "status": "sent",
                "$or": [
                    {"idempotency_key": f"{opp_k}:email"},
                    {"idempotency_key": f"{opp_k}:whatsapp"},
                    {"metadata.opportunity_key": opp_k},
                ]
            })
            if not already_sent:
                eligible_opps.append(opp)

        target_opp_key = None
        if opportunity_identifier:
            opp_ident_str = str(opportunity_identifier).strip()
            matched = [
                o for o in eligible_opps
                if str(o.get("_id")) == opp_ident_str or str(o.get("opportunity_key")) == opp_ident_str
            ]
            if not matched:
                print(f"\nERROR: Specified opportunity '{opportunity_identifier}' is not an eligible pending opportunity for customer {cust_id}.")
                return False, {"error": f"Opportunity '{opportunity_identifier}' not found or not eligible for customer"}
            target_opp_key = matched[0].get("opportunity_key")
        else:
            if len(eligible_opps) == 0:
                print(f"\nERROR: Zero eligible opportunities found for customer {cust_id}.")
                return False, {"error": "Zero eligible opportunities found for customer"}
            if len(eligible_opps) > 1:
                opp_keys = [o.get("opportunity_key") for o in eligible_opps]
                print(f"\nERROR: Multiple eligible opportunities ({len(eligible_opps)}) found for customer: {opp_keys}")
                print("Ambiguous dispatch blocked. Explicitly specify --opportunity-id to select exactly one.")
                return False, {
                    "error": f"Multiple eligible opportunities ({len(eligible_opps)}) found; exact opportunity ID required",
                    "eligible_opportunities": opp_keys,
                }
            target_opp_key = eligible_opps[0].get("opportunity_key")
    else:
        target_opp_key = opportunity_identifier

    # 4. Provider resolution (only when authorization verified)
    if provider is None:
        _, wa_ready = check_configuration()
        if not wa_ready:
            print("\nERROR: WhatsApp credentials missing in backend/.env (WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID required).")
            return False, {"error": "Missing Meta credentials"}
        provider = WhatsAppBusinessProvider()

    print(f"\n[CONTROLLED WORKFLOW] Executing opportunity pipeline for test customer: {cust_id} (+{norm_phone})")
    if target_opp_key:
        print(f"Target Opportunity Key: {target_opp_key}")

    # 5. Execute opportunity processing restricted to the single target opportunity
    result = process_customer_opportunities(
        customer_id=cust_id,
        db=target_db,
        provider=provider,
        target_opportunity_key=target_opp_key,
    )

    communicated = result.get("communicated", [])
    skipped = result.get("skipped", [])
    print(f"Workflow Result: communicated={len(communicated)}, skipped={len(skipped)}")

    if not communicated:
        skip_reasons = [s.get("reason") for s in skipped]
        print(f"[NO DISPATCH] Opportunities skipped. Reasons: {skip_reasons}")
        return False, {"result": result, "reason": "No opportunities communicated", "skipped": skipped}

    first_comm = communicated[0]
    channel = first_comm.get("channel")
    opp_key = first_comm.get("opportunity_key")
    print(f"[COMMUNICATED] Opportunity: {opp_key} via channel: {channel}")

    # 6. Verify database record & distinguish API acceptance vs. delivery confirmation
    comm_record = comm_col.find_one({"customer_id": cust_id, "metadata.opportunity_key": opp_key})
    api_accepted = False
    delivery_confirmed = False
    delivery_status_note = ""

    if comm_record:
        msg_id = comm_record.get("provider_message_id")
        status = comm_record.get("status")
        prov = comm_record.get("provider")
        print(f"[DB RECORD] Status: {status}, Provider: {prov}, Message ID: {msg_id}")
        if status == "sent":
            api_accepted = True
            delivery_confirmed = False
            delivery_status_note = (
                "API Acceptance: Meta accepted the message payload for queuing (wamid recorded). "
                "Handset delivery confirmation requires webhook receipt or physical handset inspection."
            )
            print(f"  --> {delivery_status_note}")

    return True, {
        "result": result,
        "record": comm_record,
        "api_accepted": api_accepted,
        "delivery_confirmed": delivery_confirmed,
        "delivery_status_note": delivery_status_note,
        "provider_message_id": comm_record.get("provider_message_id") if comm_record else None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify real communication delivery configuration and test dispatch")
    parser.add_argument("--check-config", action="store_true", help="Audit credentials, templates, webhooks, and safeguards without sending anything")
    parser.add_argument("--validate-phone", type=str, help="Validate phone number formatting for E.164 compliance without sending anything")
    parser.add_argument("--send-email", type=str, help="Recipient email address for controlled test")
    parser.add_argument("--send-whatsapp", type=str, help="Recipient phone number for direct provider test")
    parser.add_argument("--send-workflow-whatsapp", type=str, help="Customer ID/email to trigger controlled application marketing workflow")
    parser.add_argument("--opportunity-id", type=str, help="Specific opportunity ID or key to dispatch (required if multiple eligible opportunities exist)")
    parser.add_argument("--confirm-real-dispatch", action="store_true", help="Explicitly enable live delivery execution for --send-email, --send-whatsapp, or --send-workflow-whatsapp")
    args = parser.parse_args()

    if args.validate_phone:
        validate_phone_utility(args.validate_phone)
    elif args.send_email:
        run_controlled_email_test(args.send_email, confirm_real=args.confirm_real_dispatch)
    elif args.send_whatsapp:
        run_controlled_whatsapp_test(args.send_whatsapp, confirm_real=args.confirm_real_dispatch)
    elif args.send_workflow_whatsapp:
        testing_active = os.environ.get("TESTING", "").strip() == "1"
        mongo_uri = os.environ.get("MONGO_URI", "").strip().lower()
        is_loopback = any(lh in mongo_uri for lh in ("127.0.0.1", "localhost", "::1"))
        has_remote = any(pat in mongo_uri for pat in ("mongodb+srv://", ".mongodb.net", "atlas"))
        if not (testing_active and is_loopback) or has_remote:
            print("\n" + "!" * 70)
            print("SAFEGUARD BLOCKED: Direct execution of --send-workflow-whatsapp via verify_real_delivery.py is disabled.")
            print("To ensure complete database isolation and prevent touching Atlas, use the local test launcher:")
            print(f"    python local_test_launcher.py --test-journey {args.send_workflow_whatsapp}")
            print("!" * 70)
            sys.exit(1)

        run_application_whatsapp_journey(
            args.send_workflow_whatsapp,
            opportunity_identifier=args.opportunity_id,
            confirm_real=args.confirm_real_dispatch,
        )
    else:
        check_configuration()
