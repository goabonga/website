# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""IMAP client for connecting to Protonmail Bridge."""

import imaplib

from mailler.config import settings
from mailler.logging import get_logger

logger = get_logger(__name__)


def connect() -> imaplib.IMAP4:
    """Connect to the IMAP server (Protonmail Bridge).

    Returns:
        Authenticated IMAP4 connection.

    Raises:
        imaplib.IMAP4.error: On connection or authentication failure.
    """
    host = settings.protonmail_host
    port = settings.inbound_imap_port

    logger.debug("Connecting to IMAP", extra={"host": host, "port": port})

    imap = imaplib.IMAP4(host, port)

    # Protonmail Bridge uses STARTTLS
    imap.starttls()
    imap.login(settings.protonmail_user, settings.protonmail_password)

    logger.debug("IMAP connection established")
    return imap


def ensure_folder_exists(imap: imaplib.IMAP4, folder: str) -> None:
    """Create an IMAP folder if it does not exist.

    Args:
        imap: Active IMAP connection.
        folder: Folder name to create.
    """
    status, _ = imap.select(folder)
    if status != "OK":
        logger.info("Creating IMAP folder", extra={"folder": folder})
        imap.create(folder)
    # Go back to INBOX
    imap.select("INBOX")


def fetch_unseen_emails(imap: imaplib.IMAP4) -> list[tuple[str, bytes]]:
    """Fetch unseen emails from INBOX.

    Args:
        imap: Active IMAP connection.

    Returns:
        List of (uid, raw_email_bytes) tuples.
    """
    imap.select("INBOX")

    status, data = imap.uid("search", "ALL", "UNSEEN")
    if status != "OK" or not data[0]:
        return []

    uids = data[0].split()
    logger.info("Found unseen emails", extra={"count": len(uids)})

    results = []
    for uid in uids:
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        status, msg_data = imap.uid("fetch", uid_str, "(RFC822)")
        if status == "OK" and msg_data[0] is not None:
            raw_email = msg_data[0][1]
            if isinstance(raw_email, bytes):
                results.append((uid_str, raw_email))

    return results


def move_to_folder(imap: imaplib.IMAP4, uid: str, folder: str) -> bool:
    """Move an email to a different IMAP folder.

    Args:
        imap: Active IMAP connection.
        uid: Email UID.
        folder: Target folder name.

    Returns:
        True if move was successful, False otherwise.
    """
    try:
        # Copy to target folder
        status, _ = imap.uid("copy", uid, folder)
        if status != "OK":
            logger.error(
                "Failed to copy email to folder",
                extra={"uid": uid, "folder": folder},
            )
            return False

        # Mark original as deleted
        imap.uid("store", uid, "+FLAGS", "(\\Deleted)")
        imap.expunge()

        logger.debug("Moved email to folder", extra={"uid": uid, "folder": folder})
        return True
    except imaplib.IMAP4.error as e:
        logger.error(
            "IMAP error moving email",
            extra={"uid": uid, "folder": folder, "error": str(e)},
        )
        return False
