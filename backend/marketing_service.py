"""Marketing Automation Service handling triggers and campaign logs."""

from datetime import datetime, timedelta, timezone
from bson import ObjectId


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
        "channel": "sms",
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


def evaluate_campaign_triggers(
    campaigns_collection,
    campaign_logs_collection,
    cart_collection,
    leads_collection,
    profiles_collection
):
    """Evaluate active campaign triggers and log triggered actions."""
    seed_campaigns_if_empty(campaigns_collection)
    active_campaigns = list(campaigns_collection.find({"active": True}))

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
                anon_id = cart_item.get("anonymous_id")
                recipient = str(u_id or anon_id)

                # Check if log exists in last 24h
                already_sent = campaign_logs_collection.find_one({
                    "campaign_id": campaign["_id"],
                    "recipient": recipient,
                    "sent_at": {"$gt": now - timedelta(hours=24)}
                })
                if not already_sent:
                    log_doc = {
                        "campaign_id": campaign["_id"],
                        "campaign_name": campaign["name"],
                        "trigger_type": t_type,
                        "recipient": recipient,
                        "channel": campaign.get("channel", "email"),
                        "message": campaign.get("template", "").replace("{{name}}", recipient),
                        "status": "Sent",
                        "sent_at": now
                    }
                    campaign_logs_collection.insert_one(log_doc)
                    triggered_logs.append(log_doc)

        # 2. Hot Lead VIP Trigger
        elif t_type == "hot_lead":
            hot_leads = list(leads_collection.find({"segment": "Hot"}))
            for lead in hot_leads:
                recipient = str(lead.get("user_id") or lead.get("visitor_id"))
                already_sent = campaign_logs_collection.find_one({
                    "campaign_id": campaign["_id"],
                    "recipient": recipient
                })
                if not already_sent:
                    log_doc = {
                        "campaign_id": campaign["_id"],
                        "campaign_name": campaign["name"],
                        "trigger_type": t_type,
                        "recipient": recipient,
                        "channel": campaign.get("channel", "sms"),
                        "message": campaign.get("template", ""),
                        "status": "Sent",
                        "sent_at": now
                    }
                    campaign_logs_collection.insert_one(log_doc)
                    triggered_logs.append(log_doc)

    return triggered_logs
