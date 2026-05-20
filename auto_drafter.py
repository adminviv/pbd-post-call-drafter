#!/usr/bin/env python3
"""
Auto Post-Call Email Drafter
-----------------------------
Drafts follow-up emails for Otter meetings and sends each as a separate
email thread.

Usage:
  # Process specific meeting URL(s):
  python auto_drafter.py https://otter.ai/u/xxx https://otter.ai/u/yyy

  # Dry run (print drafts, no email sent):
  python auto_drafter.py https://otter.ai/u/xxx --test

  # Auto-discover meetings since last Friday (requires fresh Otter cookies):
  python auto_drafter.py --auto

  # Auto-discover with custom lookback window:
  python auto_drafter.py --auto --days 7

To switch from test to production:
  Change SEND_TO below to "research@pbdproject.org"
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

from draft_email import (
    check_exclusions,
    draft_email_with_groq,
    send_draft_email,
    OTTER_EMAIL,
    OTTER_PASSWORD,
)
from otter_client import (
    get_session,
    get_transcript_from_share_url,
    get_transcripts_since,
)

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
# TEST MODE  → genevieve.espra.work@gmail.com
# PRODUCTION → research@pbdproject.org
SEND_TO = "research@pbdproject.org"
# ──────────────────────────────────────────────────────────────────────────────

PROCESSED_LOG = os.path.join(os.path.dirname(__file__), "processed_urls.log")
PAUSE_FILE    = os.path.join(os.path.dirname(__file__), "PAUSED")


def get_last_friday():
    """Returns midnight of the most recent Friday."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_friday = (today.weekday() - 4) % 7
    if days_since_friday == 0:
        return today
    return today - timedelta(days=days_since_friday)


def load_processed():
    """Load set of already-processed URLs from the log file."""
    if not os.path.exists(PROCESSED_LOG):
        return set()
    with open(PROCESSED_LOG) as f:
        return set(line.strip() for line in f if line.strip())


def mark_processed(url):
    """Append a URL to the processed log so it won't be re-sent."""
    with open(PROCESSED_LOG, "a") as f:
        f.write(url.strip() + "\n")


def process_url(session, url, dry_run=False):
    """Fetch, draft, and send one transcript. Returns True if sent."""
    print(f"\n  URL: {url}")

    try:
        data = get_transcript_from_share_url(session, url)
    except Exception as e:
        print(f"  ERROR fetching transcript: {e}")
        return False

    print(f"  Meeting : {data['title']}")

    # Skip if transcript extraction clearly failed (cookie wall / login redirect)
    transcript_len = len(data.get("transcript", ""))
    generic_titles = {"meeting", "note", "otter voice meeting notes", ""}
    if transcript_len < 5000 or data.get("title", "").strip().lower() in generic_titles:
        print(f"  SKIPPED — transcript too short or no title ({transcript_len} chars). Otter session may need refresh.")
        return False

    excluded = check_exclusions(data["speakers"], title=data.get("title", ""))
    if excluded:
        print(f"  SKIPPED — {excluded}")
        return False

    print("  Drafting with Groq...")
    try:
        recipient, subject, body = draft_email_with_groq(data)
    except Exception as e:
        print(f"  ERROR drafting: {e}")
        return False

    print(f"  TO      : {recipient}")
    print(f"  SUBJECT : {subject}")
    print(f"  {'─'*50}")
    for line in body.split("\n"):
        print(f"  {line}")

    if dry_run:
        print("\n  DRY RUN — email not sent.")
        return True

    send_draft_email(
        recipient_email=recipient,
        subject=subject,
        body=body,
        otter_url=url,
        meeting_title=data["title"],
        speakers=data["speakers"],
        to=SEND_TO,
    )
    return True


def run(urls=None, auto=False, days_back=None, dry_run=False):
    # ── Check for PAUSED file ──────────────────────────────────────────────
    if os.path.exists(PAUSE_FILE):
        print("=" * 60)
        print("AUTO POST-CALL EMAIL DRAFTER — PAUSED")
        print("Remove the PAUSED file from the project folder to resume.")
        print("=" * 60)
        return

    print("=" * 60)
    print("AUTO POST-CALL EMAIL DRAFTER")
    print(f"Sending to : {SEND_TO}")
    if dry_run:
        print("Mode       : DRY RUN (no emails sent)")
    print("=" * 60)

    session = get_session(OTTER_EMAIL, OTTER_PASSWORD)

    # ── Mode 1: explicit URLs passed as arguments ──────────────────────────
    if urls:
        already_done = load_processed()
        to_run = [u for u in urls if u not in already_done]
        skipped_dup = len(urls) - len(to_run)

        if skipped_dup:
            print(f"\n{skipped_dup} URL(s) already processed — skipping.")

        if not to_run:
            print("Nothing new to process.")
            return

        print(f"\nProcessing {len(to_run)} meeting(s)...\n")
        sent = skipped = 0

        for i, url in enumerate(to_run, 1):
            print(f"[{i}/{len(to_run)}]")
            ok = process_url(session, url, dry_run=dry_run)
            if ok:
                sent += 1
                if not dry_run:
                    mark_processed(url)
            else:
                skipped += 1

        print(f"\n{'='*60}")
        print(f"DONE — {sent} sent, {skipped} skipped.")
        print("=" * 60)
        return

    # ── Mode 2: auto-discover from Otter home page ─────────────────────────
    if auto:
        if days_back is not None:
            since = datetime.now() - timedelta(days=days_back)
        else:
            since = get_last_friday()

        print(f"\nAuto-discovering meetings since {since.strftime('%A, %b %d %Y')}...")

        try:
            discovered = get_transcripts_since(session, since)
        except Exception as e:
            print(f"ERROR: Could not scan Otter home page: {e}")
            print("\nTip: Re-export your Otter cookies from Chrome (Cookie-Editor)")
            print("     and save them to otter_session.json, then retry.")
            return

        if not discovered:
            print("No meetings found since the cutoff date.")
            return

        already_done = load_processed()
        to_run = [u for u in discovered if u not in already_done]
        print(f"Found {len(discovered)} meeting(s), {len(to_run)} new.\n")

        sent = skipped = 0
        for i, url in enumerate(to_run, 1):
            print(f"[{i}/{len(to_run)}]")
            ok = process_url(session, url, dry_run=dry_run)
            if ok:
                sent += 1
                if not dry_run:
                    mark_processed(url)
            else:
                skipped += 1

        print(f"\n{'='*60}")
        print(f"DONE — {sent} sent, {skipped} skipped.")
        print("=" * 60)
        return

    print("No input given. Provide URL(s) or use --auto flag.")
    print("Run with --help for usage.")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    dry_run = "--test" in args
    auto    = "--auto" in args
    args    = [a for a in args if a not in ("--test", "--auto")]

    # --days N
    days_back = None
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            try:
                days_back = int(args[i + 1])
                args = args[:i] + args[i + 2:]
            except ValueError:
                pass
            break

    # Remaining args are URLs
    urls = [a for a in args if a.startswith("http")]

    run(urls=urls or None, auto=auto, days_back=days_back, dry_run=dry_run)
