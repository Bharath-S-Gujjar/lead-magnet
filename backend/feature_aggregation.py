"""Behavioral feature aggregation for completed visitor sessions.

This module intentionally does not import Flask, MongoDB, or any model artifact.
It turns one session document and its raw events into a plain dictionary that a
later model-adapter layer can map to the trained model's feature columns.
"""

from datetime import datetime


HIGH_INTENT_PAGE_KEYWORDS = ("pricing", "demo", "contact", "checkout")

MEANINGFUL_ACTIVITY_LABELS = {
    "page_view": "Page Visited on Website",
    "form_open": "Form Opened",
    "form_submit": "Form Submitted on Website",
    "chat": "Olark Chat Conversation",
    "chat_message": "Olark Chat Conversation",
    "lead_capture": "Converted to Lead",
}


def _event_time(event):
    """Sort missing timestamps after timestamped events while preserving order."""
    timestamp = event.get("timestamp")
    return timestamp if isinstance(timestamp, datetime) else datetime.max


def _session_duration_seconds(session):
    """Prefer the finalized duration, with a timestamp-based fallback."""
    duration = session.get("total_time_seconds")
    if isinstance(duration, (int, float)) and duration >= 0:
        return duration

    started_at = session.get("started_at")
    ended_at = session.get("ended_at") or session.get("last_active_at")
    if isinstance(started_at, datetime) and isinstance(ended_at, datetime):
        return max((ended_at - started_at).total_seconds(), 0)

    return 0


def _metadata(event):
    metadata = event.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def aggregate_session_features(session, events):
    """Return behavioral features derived from one completed session and its events.

    ``total_visits`` defaults to one because this function receives one session.
    A future caller that has a visitor-level session count can place it in the
    session document as ``total_visits`` before calling this function.
    """
    ordered_events = sorted(events, key=_event_time)
    page_view_events = [event for event in ordered_events if event.get("event_type") == "page_view"]
    click_events = [event for event in ordered_events if event.get("event_type") == "click"]
    form_open_events = [event for event in ordered_events if event.get("event_type") == "form_open"]
    form_submit_events = [event for event in ordered_events if event.get("event_type") == "form_submit"]
    scroll_events = [event for event in ordered_events if event.get("event_type") == "scroll"]

    event_page_views = len(page_view_events)
    page_views = event_page_views or session.get("page_views", 0)
    if not isinstance(page_views, int) or page_views < 0:
        page_views = 0

    total_visits = session.get("total_visits", 1)
    if not isinstance(total_visits, int) or total_visits < 1:
        total_visits = 1

    pages = [event.get("page") for event in page_view_events if event.get("page")]
    high_intent_page_visits = sum(
        any(keyword in page.lower() for keyword in HIGH_INTENT_PAGE_KEYWORDS)
        for page in pages
        if isinstance(page, str)
    )

    meaningful_events = [
        event for event in ordered_events
        if event.get("event_type") in MEANINGFUL_ACTIVITY_LABELS
    ]
    last_meaningful_event = meaningful_events[-1] if meaningful_events else None
    last_meaningful_event_type = (
        last_meaningful_event.get("event_type") if last_meaningful_event else "unknown"
    )

    max_scroll_depth = 0
    for event in scroll_events:
        scroll_depth = _metadata(event).get("scroll_depth", 0)
        if isinstance(scroll_depth, (int, float)):
            max_scroll_depth = max(max_scroll_depth, scroll_depth)

    first_event_metadata = _metadata(ordered_events[0]) if ordered_events else {}
    landing_source = (
        session.get("utm_source")
        or session.get("lead_source")
        or session.get("source")
        or first_event_metadata.get("utm_source")
        or first_event_metadata.get("referrer")
        or "unknown"
    )
    landing_page = session.get("landing_page") or (pages[0] if pages else None)

    return {
        "total_time_seconds": _session_duration_seconds(session),
        "page_views": page_views,
        "total_visits": total_visits,
        "page_views_per_visit": page_views / total_visits,
        "event_count": len(ordered_events),
        "click_count": len(click_events),
        # Current tracking only has a generic click event, so every click is
        # provisionally treated as a CTA click until CTA metadata is added.
        "cta_click_count": len(click_events),
        "form_open_count": len(form_open_events),
        "form_submit_count": len(form_submit_events),
        "scroll_event_count": len(scroll_events),
        "max_scroll_depth": max_scroll_depth,
        "high_intent_page_visits": high_intent_page_visits,
        "landing_source": landing_source,
        "landing_page": landing_page,
        "last_meaningful_event_type": last_meaningful_event_type,
        "last_meaningful_activity": MEANINGFUL_ACTIVITY_LABELS.get(
            last_meaningful_event_type, "Unknown"
        ),
    }
