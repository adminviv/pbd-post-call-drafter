#!/usr/bin/env python3
"""
PILOT TEST — runs only the 3 approved Otter links.
Safe to run — will not touch any other transcripts.
"""

from draft_email import process, send_draft_email, draft_email_with_groq, check_exclusions, OTTER_EMAIL, OTTER_PASSWORD
from otter_client import get_session, get_transcript_from_share_url

# TEST MODE:  genevieve.espra.work@gmail.com
# PRODUCTION: research@pbdproject.org
SEND_TO = "genevieve.espra.work@gmail.com"

PILOT_CALLS = [
    "https://otter.ai/u/1Llq6pqNctdQFH48Ep8fceeDYmE",
    "https://otter.ai/u/YGSRfSqTdn86TUXcn7h3nr91HSE",
    "https://otter.ai/u/RIdMC3yxz9Oouc3ijER8rtNCxRc",
]

import sys
dry_run = "--test" in sys.argv

print("=" * 60)
print("POST-CALL EMAIL DRAFTER — PILOT TEST")
print(f"Sending {len(PILOT_CALLS)} drafts to {SEND_TO}")
if dry_run:
    print("Mode: DRY RUN")
print("=" * 60)

session = get_session(OTTER_EMAIL, OTTER_PASSWORD)

for i, url in enumerate(PILOT_CALLS, 1):
    print(f"\n[{i}/{len(PILOT_CALLS)}] Processing: {url}")
    print("-" * 60)
    try:
        data = get_transcript_from_share_url(session, url)
        print(f"Meeting: {data['title']}")
        print(f"Speakers: {data['speakers']}")

        reason = check_exclusions(data["speakers"], title=data.get("title", ""))
        if reason:
            print(f"SKIPPED — {reason}")
            continue

        print("Drafting with Groq...")
        recipient, subject, body = draft_email_with_groq(data)

        print(f"\n{'─'*60}")
        print(f"OTTER:     {url}")
        print(f"TO:        {recipient}")
        print(f"SUBJECT:   {subject}")
        print(f"{'─'*60}")
        print(body)
        print(f"{'─'*60}\n")

        if dry_run:
            print("DRY RUN — not sent.")
        else:
            send_draft_email(recipient, subject, body, url, data["title"], to=SEND_TO)

    except Exception as e:
        print(f"ERROR: {e}")
        print("Continuing to next call...")

print("\n" + "=" * 60)
print("PILOT TEST COMPLETE")
print(f"Check {SEND_TO} for the 3 drafts.")
print("=" * 60)
