"""Shared next-best-action rules for lead segments."""


def get_next_action(segment):
    if segment == "Hot":
        return "Call now + send email"
    if segment == "Warm":
        return "Send email"
    return "Add to nurture list"
