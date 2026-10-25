"""Marketing Automation Service handling triggers and campaign logs."""

from datetime import datetime, timedelta, timezone
from bson import ObjectId

from canonical_lead_adapter import resolve_effective_segment


DEFAULT_CAMPAIGNS = [
    {
        "name": "Abandoned Cart Recovery",
        "trigger_type": "abandoned_cart",
        "channel": "email",
        "template": "Hi {{name}}, you left items in your cart! Complete your purchase today for 10% OFF with code CART10.",
        "active": True
    },
    {
        "name": "Hot Lead VIP Offer",
        "trigger_type": "hot_lead",
        "channel": "whatsapp",
        "template": "Exclusive VIP Deal! Use code VIP25 for 25% OFF your order. Valid for the next 2 hours!",
        "active": True
    },
    {
        "name": "Wishlist Reminder",
        "trigger_type": "wishlist_reminder",
        "channel": "email",
        "template": "Items on your wishlist are selling fast! Check out your saved favorites now.",
        "active": True
    }
]


def seed_campaigns_if_empty(campaigns_collection):
    """Initialize default marketing campaigns if collection is empty."""
    if campaigns_collection.count_documents({}) == 0:
        now = datetime.now(timezone.utc)
        for campaign in DEFAULT_CAMPAIGNS:
            campaigns_collection.insert_one({
                **campaign,
                "created_at": now,
                "updated_at": now
            })


def get_all_campaigns(campaigns_collection):
    """Retrieve all marketing campaigns."""
    seed_campaigns_if_empty(campaigns_collection)
    return list(campaigns_collection.find({}))


def create_campaign(campaigns_collection, name, trigger_type, channel, template, active=True):
    """Create a new marketing campaign."""
    now = datetime.now(timezone.utc)
    doc = {
        "name": name,
        "trigger_type": trigger_type,
        "channel": channel,
        "template": template,
        "active": active,
        "created_at": now,
        "updated_at": now
    }
    res = campaigns_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


def get_campaign_logs(campaign_logs_collection, limit=50):
    """Fetch recent campaign execution logs."""
    return list(campaign_logs_collection.find({}).sort("sent_at", -1).limit(limit))


from communication_provider import get_communication_provider
from customer_feature_service import _to_object_id


def evaluate_campaign_triggers(
    campaigns_collection,
    campaign_logs_collection,
    cart_collection,
    leads_collection=None,
    profiles_collection=None,
    customer_lead_state_collection=None,
    db=None,
    provider=None
):
    """Evaluate active campaign triggers and log triggered actions.

    Hot lead trigger selects from canonical customer_lead_state records and verifies
    channel eligibility, explicit promotional consent, and contact info before dispatching.
    Dispatches through configured communication provider, distinguishing real SMTP
    acceptance from dry-run records.
    """
    seed_campaigns_if_empty(campaigns_collection)
    active_campaigns = list(campaigns_collection.find({"active": True}))

    comm_provider = provider or get_communication_provider()

    triggered_logs = []
    now = datetime.now(timezone.utc)

    for campaign in active_campaigns:
        t_type = campaign.get("trigger_type")

        # 1. Abandoned Cart Trigger
        if t_type == "abandoned_cart":
            # Cart items older than 15 mins
            cutoff = now - timedelta(minutes=15)
            abandoned_carts = list(cart_collection.find({"updated_at": {"$lt": cutoff}}))

            for cart_item in abandoned_carts:
                u_id = cart_item.get("user_id")
                if not u_id:
                    # Anonymous cart cannot be delivered to email without customer profile
                    continue

                c_oid = _to_object_id(u_id)
                profile = None
                if profiles_collection is not None:
                    if c_oid:
                        profile = profiles_collection.find_one({"_id": c_oid})
                    if not profile:
                        or_conds = [{"_id": u_id}, {"user_id": u_id}]
                        if c_oid:
                            or_conds.append({"user_id": c_oid})
                        profile = profiles_collection.find_one({"$or": or_conds})

                channel = str(campaign.get("channel", "email")).lower()
                recipient = None
                customer_name = "Valued Customer"

                if profile:
                    customer_name = (
                        profile.get("full_name")
                        or profile.get("username")
                        or profile.get("email")
                        or customer_name
                    )
                    if channel == "email":
                        email = profile.get("email")
                        opt_out = profile.get("email_opt_out", False)
                        if email and "@" in str(email) and not opt_out:
                            recipient = str(email).strip()
                    elif channel == "whatsapp":
                        phone = profile.get("phone")
                        opt_out = profile.get("whatsapp_opt_out", False)
                        has_consent = bool(
                            profile.get("whatsapp_promotional_consent")
                            or profile.get("whatsapp_opt_in")
                        )
                        if phone and not opt_out and has_consent:
                            recipient = str(phone).strip()

                if not recipient:
                    continue

                # Check if log exists in last 24h
                already_sent = campaign_logs_collection.find_one({
                    "campaign_id": campaign["_id"],
                    "recipient": recipient,
                    "sent_at": {"$gt": now - timedelta(hours=24)}
                })
                if not already_sent:
                    msg_body = campaign.get("template", "").replace("{{name}}", customer_name)
                    subject = campaign.get("name") or "Complete Your Order — Lead Magnet"

                    if channel == "email":
                        prov_res = comm_provider.send_email(
                            recipient,
                            subject,
                            msg_body,
                            metadata={"campaign_id": str(campaign["_id"]), "trigger_type": t_type}
                        )
                    elif channel == "whatsapp":
                        prov_res = comm_provider.send_whatsapp(
                            recipient,
                            msg_body,
                            metadata={"campaign_id": str(campaign["_id"]), "trigger_type": t_type}
                        )
                    else:
                        prov_res = {"success": False, "error": f"Unsupported channel: {channel}", "provider": "unsupported"}

                    prov_success = bool(prov_res.get("success", False))
                    prov_name = prov_res.get("provider", "unknown")
                    prov_msg_id = prov_res.get("provider_message_id")
                    prov_err = prov_res.get("error")

                    if not prov_success:
                        status = "Failed"
                    elif prov_name == "dry_run" and channel == "email":
                        status = "Dry Run"
                    else:
                        status = "Sent"

                    log_doc = {
                        "campaign_id": campaign["_id"],
                        "campaign_name": campaign["name"],
                        "trigger_type": t_type,
                        "customer_id": str(u_id),
                        "recipient": recipient,
                        "channel": channel,
                        "message": msg_body,
                        "provider": prov_name,
                        "provider_message_id": prov_msg_id,
                        "provider_result": prov_res,
                        "status": status,
                        "error": prov_err,
                        "sent_at": now if prov_success else None,
                        "created_at": now,
                    }
                    campaign_logs_collection.insert_one(log_doc)
                    triggered_logs.append(log_doc)

        # 2. Hot Lead VIP Trigger
        elif t_type == "hot_lead":
            target_lead_col = customer_lead_state_collection
            if target_lead_col is None:
                if db is not None and hasattr(db, "__getitem__"):
                    try:
                        target_lead_col = db["customer_lead_state"]
                    except Exception:
                        pass
            if target_lead_col is None:
                target_lead_col = leads_collection

            if target_lead_col is not None:
                try:
                    hot_leads = list(target_lead_col.find({
                        "$or": [
                            {"lead_segment": {"$in": ["Hot", "hot"]}},
                            {
                                "$and": [
                                    {"lead_segment": {"$exists": False}},
                                    {"segment": {"$in": ["Hot", "hot"]}}
                                ]
                            }
                        ]
                    }))
                except Exception:
                    hot_leads = []
            else:
                hot_leads = []

            for lead in hot_leads:
                effective_segment = resolve_effective_segment(lead)
                if effective_segment != "Hot":
                    continue

                c_id = lead.get("customer_id") or lead.get("user_id") or lead.get("visitor_id")
                if not c_id:
                    continue

                c_oid = _to_object_id(c_id)

                profile = None
                if profiles_collection is not None:
                    if c_oid:
                        profile = profiles_collection.find_one({"_id": c_oid})
                    if not profile:
                        or_conds = [{"_id": c_id}, {"user_id": c_id}]
                        if c_oid:
                            or_conds.append({"user_id": c_oid})
                        profile = profiles_collection.find_one({"$or": or_conds})

                channel = str(campaign.get("channel", "whatsapp")).lower()
                is_eligible = False
                recipient = None
                customer_name = "Valued Customer"

                if profile:
                    customer_name = (
                        profile.get("full_name")
                        or profile.get("username")
                        or profile.get("email")
                        or customer_name
                    )
                    if channel == "whatsapp":
                        phone = profile.get("phone")
                        opt_out = profile.get("whatsapp_opt_out", False)
                        has_consent = bool(
                            profile.get("whatsapp_promotional_consent")
                            or profile.get("whatsapp_opt_in")
                        )
                        if phone and not opt_out and has_consent:
                            is_eligible = True
                            recipient = str(phone).strip()
                    elif channel == "email":
                        email = profile.get("email")
                        opt_out = profile.get("email_opt_out", False)
                        if email and "@" in str(email) and not opt_out:
                            is_eligible = True
                            recipient = str(email).strip()
                    else:
                        recipient = profile.get("phone") or profile.get("email")
                        if recipient:
                            is_eligible = True
                else:
                    if channel == "whatsapp":
                        phone = lead.get("phone")
                        has_consent = bool(
                            lead.get("whatsapp_promotional_consent")
                            or lead.get("whatsapp_opt_in")
                        )
                        opt_out = lead.get("whatsapp_opt_out", False)
                        if phone and has_consent and not opt_out:
                            is_eligible = True
                            recipient = str(phone).strip()
                    elif channel == "email":
                        email = lead.get("email")
                        opt_out = lead.get("email_opt_out", False)
                        if email and "@" in str(email) and not opt_out:
                            is_eligible = True
                            recipient = str(email).strip()

                if not is_eligible or not recipient:
                    continue

                already_sent = campaign_logs_collection.find_one({
                    "campaign_id": campaign["_id"],
                    "recipient": recipient
                })
                if not already_sent:
                    msg_body = campaign.get("template", "").replace("{{name}}", customer_name)
                    subject = campaign.get("name") or "Exclusive VIP Offer — Lead Magnet"

                    if channel == "email":
                        prov_res = comm_provider.send_email(
                            recipient,
                            subject,
                            msg_body,
                            metadata={"campaign_id": str(campaign["_id"]), "trigger_type": t_type}
                        )
                    elif channel == "whatsapp":
                        prov_res = comm_provider.send_whatsapp(
                            recipient,
                            msg_body,
                            metadata={"campaign_id": str(campaign["_id"]), "trigger_type": t_type}
                        )
                    else:
                        prov_res = {"success": False, "error": f"Unsupported channel: {channel}", "provider": "unsupported"}

                    prov_success = bool(prov_res.get("success", False))
                    prov_name = prov_res.get("provider", "unknown")
                    prov_msg_id = prov_res.get("provider_message_id")
                    prov_err = prov_res.get("error")

                    if not prov_success:
                        status = "Failed"
                    elif prov_name == "dry_run" and channel == "email":
                        status = "Dry Run"
                    else:
                        status = "Sent"

                    log_doc = {
                        "campaign_id": campaign["_id"],
                        "campaign_name": campaign["name"],
                        "trigger_type": t_type,
                        "customer_id": str(c_id),
                        "recipient": recipient,
                        "channel": channel,
                        "message": msg_body,
                        "provider": prov_name,
                        "provider_message_id": prov_msg_id,
                        "provider_result": prov_res,
                        "status": status,
                        "error": prov_err,
                        "sent_at": now if prov_success else None,
                        "created_at": now,
                    }
                    campaign_logs_collection.insert_one(log_doc)
                    triggered_logs.append(log_doc)

        # 3. Wishlist Reminder Trigger
        elif t_type == "wishlist_reminder":
            wishlist_col = None
            if db is not None and hasattr(db, "__getitem__"):
                try:
                    wishlist_col = db["wishlist"]
                except Exception:
                    pass

            if wishlist_col is not None:
                # Find non-empty wishlists
                active_wishlists = list(wishlist_col.find({"items.0": {"$exists": True}}))
                for wl in active_wishlists:
                    u_id = wl.get("user_id")
                    if not u_id:
                        continue

                    c_oid = _to_object_id(u_id)
                    profile = None
                    if profiles_collection is not None:
                        if c_oid:
                            profile = profiles_collection.find_one({"_id": c_oid})
                        if not profile:
                            or_conds = [{"_id": u_id}, {"user_id": u_id}]
                            if c_oid:
                                or_conds.append({"user_id": c_oid})
                            profile = profiles_collection.find_one({"$or": or_conds})

                    channel = str(campaign.get("channel", "email")).lower()
                    recipient = None
                    customer_name = "Valued Customer"

                    if profile:
                        customer_name = (
                            profile.get("full_name")
                            or profile.get("username")
                            or profile.get("email")
                            or customer_name
                        )
                        if channel == "email":
                            email = profile.get("email")
                            opt_out = profile.get("email_opt_out", False)
                            if email and "@" in str(email) and not opt_out:
                                recipient = str(email).strip()
                        elif channel == "whatsapp":
                            phone = profile.get("phone")
                            opt_out = profile.get("whatsapp_opt_out", False)
                            has_consent = bool(
                                profile.get("whatsapp_promotional_consent")
                                or profile.get("whatsapp_opt_in")
                            )
                            if phone and not opt_out and has_consent:
                                recipient = str(phone).strip()

                    if not recipient:
                        continue

                    already_sent = campaign_logs_collection.find_one({
                        "campaign_id": campaign["_id"],
                        "recipient": recipient,
                        "sent_at": {"$gt": now - timedelta(days=7)}
                    })
                    if not already_sent:
                        msg_body = campaign.get("template", "").replace("{{name}}", customer_name)
                        subject = campaign.get("name") or "Your Wishlist Items Are Selling Fast — Lead Magnet"

                        if channel == "email":
                            prov_res = comm_provider.send_email(
                                recipient,
                                subject,
                                msg_body,
                                metadata={"campaign_id": str(campaign["_id"]), "trigger_type": t_type}
                            )
                        elif channel == "whatsapp":
                            prov_res = comm_provider.send_whatsapp(
                                recipient,
                                msg_body,
                                metadata={"campaign_id": str(campaign["_id"]), "trigger_type": t_type}
                            )
                        else:
                            prov_res = {"success": False, "error": f"Unsupported channel: {channel}", "provider": "unsupported"}

                        prov_success = bool(prov_res.get("success", False))
                        prov_name = prov_res.get("provider", "unknown")
                        prov_msg_id = prov_res.get("provider_message_id")
                        prov_err = prov_res.get("error")

                        if not prov_success:
                            status = "Failed"
                        elif prov_name == "dry_run" and channel == "email":
                            status = "Dry Run"
                        else:
                            status = "Sent"

                        log_doc = {
                            "campaign_id": campaign["_id"],
                            "campaign_name": campaign["name"],
                            "trigger_type": t_type,
                            "customer_id": str(u_id),
                            "recipient": recipient,
                            "channel": channel,
                            "message": msg_body,
                            "provider": prov_name,
                            "provider_message_id": prov_msg_id,
                            "provider_result": prov_res,
                            "status": status,
                            "error": prov_err,
                            "sent_at": now if prov_success else None,
                            "created_at": now,
                        }
                        campaign_logs_collection.insert_one(log_doc)
                        triggered_logs.append(log_doc)

    return triggered_logs
