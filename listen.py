import json
import logging
import re
from copy import deepcopy as copy
from pprint import pprint

import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from util import blocks

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Load config
with open("config.json", "r") as f:
    config: dict = json.load(f)

# Debug info
debug_slack_id = None
debug_tidyhq_id = None
if config["debug"]:
    debug_slack_id = "UC6T4U150"
    debug_tidyhq_id = 1952718
    config["slack"]["admin_channel"] = "C05HB2Z82CT"

app = App(token=config["slack"]["bot_token"])


@app.action("view_invoices_admin")
def view_invoices_admin(ack, body, logger):
    # We don't actually need to do anything here. This is a link button (instead of just a link) purely for display purposes.
    ack()


@app.action("slack_remind")
def slack_remind_button(ack, body, logger):
    ack()

    # Retrieve the target's slack user ID and tidyhq contact ID
    tidyhq_id, slack_id = body["actions"][0]["value"].split("_")

    # Redirect IDs if debugging
    if debug_slack_id:
        slack_id = debug_slack_id

    if debug_tidyhq_id:
        tidyhq_id = debug_tidyhq_id

    # Iterate over the message blocks to get data for our message
    header: str = ""
    old_message: str = ""
    for block in body["message"]["blocks"]:
        if block["block_id"] == "header":
            header = block["text"]["text"]
        elif block["block_id"] == "message":
            old_message = block["text"]["text"]

    message: str = ""
    if header and old_message:
        # The original header included the members name so we'll replace it with you
        parts = header.split("$")
        message = f"As a reminder you have an outstanding balance of ${parts[1]}. (Excluding invoices that aren't at least 7 days overdue)"

        # Get the contact's name
        name = header.split(" owes $")[0]

        # Get the total invoice amount
        total_owed = parts[1].split(".")[0]

        # The original message included internal links that only work for admins, replace them with the public version
        message += f"\n\n{old_message.replace('https://artifactory.tidyhq.com/finances/invoices/', 'https://artifactory.tidyhq.com/public/invoices/')}"

        # Set up blocks
        block_list: list[dict] = []

        # Add message
        block_list.append(copy(blocks.text))
        block_list[-1]["text"]["text"] = message
        block_list[-1]["block_id"] = "message"

        # Add divider
        block_list.append(copy(blocks.divider))

        block_list.append(copy(blocks.text))
        block_list[-1]["text"]["text"] = "How would you like to proceed?"

        # Set up action block
        action_block = copy(blocks.actions)

        # Create pay invoices button
        pay_invoices_button = copy(blocks.link_button)
        pay_invoices_button["text"]["text"] = "Pay"
        pay_invoices_button["url"] = f"https://artifactory.tidyhq.com/member/invoices"
        pay_invoices_button["action_id"] = "view_invoices"
        pay_invoices_button["value"] = f"{tidyhq_id}_{slack_id}"
        pay_invoices_button["style"] = "primary"

        # Create have paid invoices button
        paid_invoices_button = copy(blocks.button)
        paid_invoices_button["text"]["text"] = "I've already paid"
        paid_invoices_button["action_id"] = "already_paid"
        paid_invoices_button["value"] = f"{tidyhq_id}_{slack_id}"

        # Create need help button
        need_help_button = copy(blocks.button)
        need_help_button["text"]["text"] = "Unable to pay (contact)"
        need_help_button["value"] = f"{tidyhq_id}_{slack_id}"
        need_help_button["action_id"] = "need_help"

        # Create looks wrong button
        looks_wrong_button = copy(blocks.button)
        looks_wrong_button["text"]["text"] = "This looks wrong (contact)"
        looks_wrong_button["value"] = f"{tidyhq_id}_{slack_id}"
        looks_wrong_button["action_id"] = "looks_wrong"

        # Add buttons to action block
        action_block["elements"].append(pay_invoices_button)
        action_block["elements"].append(paid_invoices_button)
        action_block["elements"].append(need_help_button)
        action_block["elements"].append(looks_wrong_button)

        # Add action block to block list
        block_list.append(action_block)

        # Open a slack conversation with the member and get the channel ID
        r: SlackResponse = app.client.conversations_open(users=slack_id)  # type: ignore
        channel_id: str = str(r["channel"]["id"])  # type: ignore

        # Notify the member
        app.client.chat_postMessage(  # type: ignore
            channel=channel_id,
            text=message,
            blocks=block_list,
        )

        # Send notification to admin channel that member has been reminded
        app.client.chat_postMessage(  # type: ignore
            channel=config["slack"]["admin_channel"],
            text=f"<@{slack_id}> has been reminded to pay their <https://artifactory.tidyhq.com/contacts/{tidyhq_id}/finances|invoices> by <@{body['user']['id']}> via slack.",
        )

        # Add a note to each invoice in TidyHQ that a reminder has been sent

        # Get the IDs of each invoice
        p = re.compile(r"/invoices/([a-zA-Z0-9_]*)")
        invoice_ids = p.findall(old_message)

        for invoice_id in invoice_ids:
            r = requests.post(
                config["urls"]["invoice_note"].format(invoice_id),
                params={
                    "access_token": config["tidyhq"]["token"],
                    "text": f"{name} was reminded about this invoice via Slack (User: {slack_id}).",
                },
            )
            print(r.status_code)


@app.action("tidyhq_remind")
def tidyhq_remind_button(ack, body, logger):
    ack()

    # Retrieve the target's slack user ID (junk) and tidyhq contact ID
    tidyhq_id, slack_id = body["actions"][0]["value"].split("_")

    # Redirect IDs if debugging
    if debug_slack_id:
        slack_id = debug_slack_id

    if debug_tidyhq_id:
        tidyhq_id = debug_tidyhq_id

    # Iterate over the message blocks to get data for our message
    header: str = ""
    old_message: str = ""
    for block in body["message"]["blocks"]:
        if block["block_id"] == "header":
            header = block["text"]["text"]
        elif block["block_id"] == "message":
            old_message = block["text"]["text"]

    if header and old_message:
        # Get the contact's name
        name = header.split(" owes $")[0]

        # The original header included the members name so we'll replace it with you
        parts = header.split("$")
        message = f"Hello {name},\n\nAs a reminder you have an outstanding balance of ${parts[1]}. (Excluding invoices that aren't at least 7 days overdue)"

        # Get the total invoice amount
        total_owed = parts[1].split(".")[0]

        # The original message included internal links that only work for admins, replace them with the public version
        message += f"\n\n{old_message.replace('https://artifactory.tidyhq.com/finances/invoices/', 'https://artifactory.tidyhq.com/public/invoices/')}"

        # Slack urls need to be reformatted for HTML/email
        message = (
            message.replace("<", "<a href='").replace("|", "'>").replace(">", "</a>")
        )

        message += '\n\nIf you have any questions or concerns, please don\'t hesitate to reach out to us at <a href="mailto:treasurer@artifactory.org.au">treasurer@artifactory.org.au</a>.\n\nThank you for your support,\nArtifactory Committee'

        # Since this is being sent via an email replace newlines with <br> tags
        message = message.replace("\n", "<br>")

        # Send a reminder via TidyHQ
        r = requests.post(
            config["urls"]["emails"],
            params={
                "access_token": config["tidyhq"]["token"],
                "subject": "Reminder: You have outstanding invoices with the Artifactory",
                "body": message,
                "contacts": [tidyhq_id],
            },
        )

        # Send notification to admin channel that member has been reminded
        app.client.chat_postMessage(  # type: ignore
            channel=config["slack"]["admin_channel"],
            text=f"{name} has been reminded to pay their <https://artifactory.tidyhq.com/contacts/{tidyhq_id}/finances|invoices> by <@{body['user']['id']}> via email.",
        )

        # Add a note to each invoice in TidyHQ that a reminder has been sent

        # Get the IDs of each invoice
        p = re.compile(r"/invoices/([a-zA-Z0-9_]*)")
        invoice_ids = p.findall(old_message)

        for invoice_id in invoice_ids:
            r = requests.post(
                config["urls"]["invoice_note"].format(invoice_id),
                params={
                    "access_token": config["tidyhq"]["token"],
                    "text": f"{name} was reminded about this invoice via email.",
                },
            )


@app.action("delete_invoices")
def delete_invoices(ack, body, logger):
    ack()

    # Retrieve the target's slack user ID (junk) and tidyhq contact ID
    tidyhq_id, slack_id = body["actions"][0]["value"].split("_")

    # Redirect IDs if debugging
    if debug_slack_id:
        slack_id = debug_slack_id

    if debug_tidyhq_id:
        tidyhq_id = debug_tidyhq_id

    # Iterate over the message blocks to get data for our message
    header: str = ""
    old_message: str = ""
    for block in body["message"]["blocks"]:
        if block["block_id"] == "header":
            header = block["text"]["text"]
        elif block["block_id"] == "message":
            old_message = block["text"]["text"]

    if header and old_message:
        # Get the contact's name
        name = header.split(" owes $")[0]

        # The original header included the members name so we'll replace it with you
        parts = header.split("$")
        message = f"Hello {name},\n\nAs a reminder you have an outstanding balance of ${parts[1]}. (Excluding invoices that aren't at least 7 days overdue)"

        # Get the total invoice amount
        total_owed = parts[1].split(".")[0]

        # Delete each listed invoice

        # Get the IDs of each invoice
        p = re.compile(r"/invoices/([a-zA-Z0-9_]*)")
        invoice_ids = p.findall(old_message)

        for invoice_id in invoice_ids:
            # Delete the invoice
            r = requests.delete(
                config["urls"]["invoice"].format(invoice_id),
                params={
                    "access_token": config["tidyhq"]["token"],
                },
            )

            # Leave a note on the invoice that it was deleted
            r = requests.post(
                config["urls"]["invoice_note"].format(invoice_id),
                params={
                    "access_token": config["tidyhq"]["token"],
                    "text": f"This invoice was deleted by {slack_id} via Slack.",
                },
            )

            app.client.chat_postMessage(  # type: ignore
                channel=config["slack"]["admin_channel"],
                text=f"<https://artifactory.tidyhq.com/finances/invoices/{invoice_id}|An invoice> for {name} was deleted by <@{body['user']['id']}>.",
            )


@app.action("view_invoices")
def view_invoices(ack, body, logger):
    ack()

    # Retrieve the target's slack user ID and tidyhq contact ID
    tidyhq_id, slack_id = body["actions"][0]["value"].split("_")

    # Redirect IDs if debugging
    if debug_slack_id:
        slack_id = debug_slack_id

    if debug_tidyhq_id:
        tidyhq_id = debug_tidyhq_id

    # Send notification to admin channel that member is paying
    app.client.chat_postMessage(  # type: ignore
        channel=config["slack"]["admin_channel"],
        text=f"<@{slack_id}> has agreed to pay their <https://artifactory.tidyhq.com/contacts/{tidyhq_id}/finances|invoices>",
    )

    # Thank the user
    app.client.chat_postEphemeral(  # type: ignore
        channel=body["container"]["channel_id"],
        user=slack_id,
        text="Thank you for paying, your support is greatly appreciated!",
    )


@app.action("already_paid")
def already_paid(ack, body, logger):
    ack()
    # Retrieve the target's slack user ID and tidyhq contact ID
    tidyhq_id, slack_id = body["actions"][0]["value"].split("_")

    # Redirect IDs if debugging
    if debug_slack_id:
        slack_id = debug_slack_id

    if debug_tidyhq_id:
        tidyhq_id = debug_tidyhq_id

    # Send notification to admin channel that member is paying
    app.client.chat_postMessage(  # type: ignore
        channel=config["slack"]["admin_channel"],
        text=f"<@{slack_id}> has indicated that they've already paid their <https://artifactory.tidyhq.com/contacts/{tidyhq_id}/finances|invoices>",
    )

    # Thank the user
    app.client.chat_postEphemeral(  # type: ignore
        channel=body["container"]["channel_id"],
        user=slack_id,
        text="Thanks for letting us know you've already paid. Payments made via bank transfer will be reconciled within a few days.",
    )


@app.action("need_help")
def need_help(ack, body, logger):
    ack()

    admin_contact = ",".join([config["slack"]["admins"]["treasurer"]])

    # Format the admin contact list for display
    admin_contact_formatted = ", ".join(f"<@{id}>" for id in admin_contact.split(","))

    # Retrieve the target's slack user ID and tidyhq contact ID
    tidyhq_id, slack_id = body["actions"][0]["value"].split("_")

    # Redirect IDs if debugging
    if debug_slack_id:
        slack_id = debug_slack_id

    if debug_tidyhq_id:
        tidyhq_id = debug_tidyhq_id

    # Open a slack conversation with the member and get the channel ID
    r = app.client.conversations_open(users=",".join([slack_id, admin_contact]))
    channel_id = r["channel"]["id"]

    block_list = []
    block_list.append(copy(blocks.text))
    block_list[-1]["text"][
        "text"
    ] = f"<@{slack_id}> has indicated they're unable to pay their outstanding invoices."

    block_list.append(copy(blocks.divider))

    # Retrieve invoice details from the body of the message and add them to the new message for context
    for block in body["message"]["blocks"]:
        if block["block_id"] == "message":
            block_list.append(copy(blocks.text))
            original_text = block["text"]["text"]
            invoices = original_text.split("\n\n")[1]
            block_list[-1]["text"]["text"] = invoices
            block_list[-1]["block_id"] = "message"

    # Post an opener to the DM
    app.client.chat_postMessage(  # type: ignore
        channel=channel_id,
        text=f"<@{slack_id}> has indicated they're unable to pay their outstanding invoices.",
        blocks=block_list,
    )

    # Send an ephemeral message to the user to let them know we've opened a conversation with the treasurer
    app.client.chat_postEphemeral(  # type: ignore
        channel=channel_id,
        user=slack_id,
        text=f"This is a direct message to the treasurer ({admin_contact_formatted}) to let them know you need help. They'll be in touch soon.",
    )

    # Notify the admin channel that the member needs help and a conversation has been opened
    app.client.chat_postMessage(  # type: ignore
        channel=config["slack"]["admin_channel"],
        text=f"<@{slack_id}> has indicated there's something wrong with their <https://artifactory.tidyhq.com/contacts/{tidyhq_id}/finances|outstanding invoices> and a conversation has been opened between them and: {admin_contact_formatted}",
    )

    # pprint(body)


@app.action("looks_wrong")
def looks_wrong(ack, body, logger):
    ack()

    admin_contact = ",".join(
        [
            config["slack"]["admins"]["treasurer"],
            config["slack"]["admins"]["membership"],
        ]
    )

    # Format the admin contact list for display
    admin_contact_formatted = ", ".join(f"<@{id}>" for id in admin_contact.split(","))

    # Retrieve the target's slack user ID and tidyhq contact ID
    tidyhq_id, slack_id = body["actions"][0]["value"].split("_")

    # Redirect IDs if debugging
    if debug_slack_id:
        slack_id = debug_slack_id

    if debug_tidyhq_id:
        tidyhq_id = debug_tidyhq_id

    # Open a slack conversation with the member and get the channel ID
    r = app.client.conversations_open(users=",".join([slack_id, admin_contact]))
    channel_id = r["channel"]["id"]

    block_list = []
    block_list.append(copy(blocks.text))
    block_list[-1]["text"][
        "text"
    ] = f"<@{slack_id}> has indicated there's something wrong with their outstanding invoices."

    block_list.append(copy(blocks.divider))

    # Retrieve invoice details from the body of the message and add them to the new message for context
    for block in body["message"]["blocks"]:
        if block["block_id"] == "message":
            block_list.append(copy(blocks.text))
            original_text = block["text"]["text"]
            invoices = original_text.split("\n\n")[1]
            block_list[-1]["text"]["text"] = invoices
            block_list[-1]["block_id"] = "message"

    # Post an opener to the DM
    app.client.chat_postMessage(  # type: ignore
        channel=channel_id,
        text=f"<@{slack_id}> has indicated there's something wrong with their outstanding invoices.",
        blocks=block_list,
    )

    # Send an ephemeral message to the user to let them know we've opened a conversation with the treasurer
    app.client.chat_postEphemeral(  # type: ignore
        channel=channel_id,
        user=slack_id,
        text=f"This is a direct message to the treasurer and membership officer ({admin_contact_formatted}) to let them know you need help. They'll be in touch soon.",
    )

    # Notify the admin channel that the member needs help and a conversation has been opened
    app.client.chat_postMessage(  # type: ignore
        channel=config["slack"]["admin_channel"],
        text=f"<@{slack_id}> has indicated there's something wrong with their <https://artifactory.tidyhq.com/contacts/{tidyhq_id}/finances|outstanding invoices> and a conversation has been opened between them and: {admin_contact_formatted}",
    )


# Open socket mode
if __name__ == "__main__":
    SocketModeHandler(app, config["slack"]["app_token"]).start()
