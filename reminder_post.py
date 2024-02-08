import json
import requests
import logging
import sys
from pprint import pprint
from datetime import datetime, timedelta
from copy import deepcopy as copy
from slack_bolt import App

from util import blocks

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Load config
with open("config.json", "r") as f:
    config: dict = json.load(f)

# Debug channel
if config["debug"]:
    config["slack"]["admin_channel"] = "C05HB2Z82CT"

# Set up Slack app
app = App(token=config["slack"]["bot_token"])

# Get a list of all invoices
try:
    # create datetime for 90 days ago
    query_date = datetime.now() - timedelta(days=90)
    logging.info("Getting invoices from TidyHQ")
    r = requests.get(
        config["urls"]["invoices"],
        params={
            "access_token": config["tidyhq"]["token"],
            "limit": 10000,
            "updated_since": query_date.isoformat(),
        },
    )
    invoices = r.json()
except requests.exceptions.RequestException as e:
    logging.error("Could not reach TidyHQ")
    sys.exit(1)

logging.debug(f"Found {len(invoices)} invoices")

# Trim invoices to only include those that have not been paid
invoices = [invoice for invoice in invoices if not invoice["paid"]]

# TidyHQ includes a lot of extra data in the invoices, so we'll trim it down to just the fields we need
from datetime import datetime

invoices = [
    {
        "id": invoice["id"],
        "amount": invoice["outstanding_amount"],
        "due_date": datetime.strptime(invoice["due_date"], "%Y-%m-%d"),
        "contact_id": invoice["contact"]["contact_id_reference"],
        "contact": invoice["contact"],
        "name": invoice["name"],
    }
    for invoice in invoices
]

# Collate the invoices by contact
contacts = {}
for invoice in invoices:
    if invoice["contact_id"] in contacts:
        contacts[invoice["contact_id"]].append(invoice)
    else:
        contacts[invoice["contact_id"]] = [invoice]

logging.debug(f"Collated invoices by contact, found {len(contacts)} contacts")

# Clarify that this is only for contacts with invoices at least 7 days overdue

app.client.chat_postMessage(  # type: ignore
    channel=config["slack"]["admin_channel"],
    text="This is a list of contacts with invoices at least 7 days overdue.",
)

# Iterate over contacts and look for invoices that are at least 7 days overdue

for contact in contacts:
    overdue_invoices = []
    contact_info = None
    for invoice in contacts[contact]:
        if datetime.now() - invoice["due_date"] > timedelta(days=7):
            overdue_invoices.append(invoice)
        contact_info = invoice["contact"]

    if overdue_invoices and contact_info:
        # Set up block list
        block_list = []

        # Start building the invoice list
        inv_list = []

        total_owed = 0
        for invoice in overdue_invoices:
            # Add to the running total for the top message
            total_owed += invoice["amount"]

            # Add to the list
            inv_list.append(
                f"${invoice['amount']} - <https://artifactory.tidyhq.com/finances/invoices/{invoice['id']}|{invoice['name']}> (Due {(datetime.now() - invoice['due_date']).days} days ago)"
            )

        text = f"{contact_info['display_name']} owes ${total_owed} across {len(overdue_invoices)} {'invoice' if len(overdue_invoices) == 1 else 'invoices'}"

        # Add text block
        block_list.append(copy(blocks.text))
        block_list[-1]["text"]["text"] = text
        block_list[-1]["block_id"] = "header"

        # Add divider
        block_list.append(copy(blocks.divider))

        # Add list
        block_list.append(copy(blocks.text))
        block_list[-1]["text"]["text"] = "• " + "\n• ".join(inv_list)
        block_list[-1]["block_id"] = "message"

        # Add divider
        block_list.append(copy(blocks.divider))

        # Set up action block
        action_block = copy(blocks.actions)

        # Set up confirm object
        confirm = copy(blocks.confirm)
        confirm["title"]["text"] = "Are you sure?"
        confirm["text"][
            "text"
        ] = f"This will send a reminder to {contact_info['display_name']}. Make sure that there aren't any pending bank transactions from this contact and that they haven't already been reminded recently."
        confirm["confirm"]["text"] = "Yes, remind them"
        confirm["deny"]["text"] = "No, abort"

        # Check if the contact has a Slack ID
        if contact_info["custom_fields"].get(
            config["tidyhq"]["IDs"]["slack"], {"value": None}
        )["value"]:
            slack_id = contact_info["custom_fields"][config["tidyhq"]["IDs"]["slack"]][
                "value"
            ]

            # Create remind button
            slack_remind_button = copy(blocks.button)
            slack_remind_button["text"]["text"] = "Remind via Slack"
            slack_remind_button["value"] = f"{contact}_{slack_id}"
            slack_remind_button["action_id"] = "slack_remind"
            slack_remind_button["confirm"] = confirm

            # Add remind button to action block
            action_block["elements"].append(slack_remind_button)

        # Create remind button
        tidyhq_remind_button = copy(blocks.button)
        tidyhq_remind_button["text"]["text"] = "Remind via TidyHQ"
        tidyhq_remind_button["value"] = f"{contact}_NOSLACKID"
        tidyhq_remind_button["action_id"] = "tidyhq_remind"
        tidyhq_remind_button["confirm"] = confirm

        # Add remind button to action block
        action_block["elements"].append(tidyhq_remind_button)

        # Create view invoices button
        view_invoices_button = copy(blocks.link_button)
        view_invoices_button["text"]["text"] = "View Invoices"
        view_invoices_button["url"] = (
            f"https://artifactory.tidyhq.com/contacts/{contact}/finances"
        )
        view_invoices_button["action_id"] = "view_invoices_admin"
        view_invoices_button["value"] = str(contact)

        # Add view invoices button to action block
        action_block["elements"].append(view_invoices_button)

        # Create delete invoices button
        delete_invoices_button = copy(blocks.button)
        delete_invoices_button["text"]["text"] = "Delete invoices"
        delete_invoices_button["value"] = f"{contact}_NOSLACKID"
        delete_invoices_button["action_id"] = "delete_invoices"
        delete_invoices_button["style"] = "danger"

        # Set up confirm object
        delete_confirm = copy(blocks.confirm)
        delete_confirm["title"]["text"] = "Delete listed invoices?"
        delete_confirm["text"][
            "text"
        ] = f"This will delete the listed invoices for {contact_info['display_name']} totalling ${total_owed}. This process cannot be undone."
        delete_confirm["confirm"]["text"] = "Yes, delete them"
        delete_confirm["deny"]["text"] = "No, abort"
        delete_confirm["style"] = "danger"  # type: ignore

        # Add confirm object to delete button
        delete_invoices_button["confirm"] = delete_confirm

        # Add delete invoices button to action block
        action_block["elements"].append(delete_invoices_button)

        # Add action block to block list
        block_list.append(action_block)

        # Send Slack message
        app.client.chat_postMessage(  # type: ignore
            channel=config["slack"]["admin_channel"],
            text=text,
            blocks=block_list,
        )
