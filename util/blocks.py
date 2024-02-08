button = {
    "type": "button",
    "text": {"type": "plain_text", "text": "BUTTON TEXT", "emoji": True},
    "value": "BUTTON VALUE",
    "action_id": "BUTTON ACTION ID",
}
link_button = {
    "type": "button",
    "text": {"type": "plain_text", "text": "BUTTON TEXT", "emoji": True},
    "value": "BUTTON VALUE",
    "url": "BUTTON URL",
    "action_id": "BUTTON ACTION ID",
}

list_item = {
    "type": "rich_text_section",
    "elements": [{"type": "text", "text": "TEXT"}],
}

list = {
    "type": "rich_text_list",
    "style": "bullet",
    "elements": [],
}

rich_text_section = {
    "type": "rich_text",
    "elements": [],
}

text = {
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": "",
    },
}

divider = {"type": "divider"}

actions = {"type": "actions", "elements": []}

confirm = {
    "title": {"type": "plain_text", "text": ""},
    "text": {"type": "plain_text", "text": ""},
    "confirm": {"type": "plain_text", "text": ""},
    "deny": {"type": "plain_text", "text": ""},
}
