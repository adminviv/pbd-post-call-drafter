#!/usr/bin/env python3
"""
PILOT TEST — Manual transcript input.
Reads transcript from a text file, drafts email, sends to research@pbdproject.org.

Usage:
  python3 pilot_manual.py transcript1.txt
  python3 pilot_manual.py transcript1.txt --test    (dry run, no email sent)
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")
GMAIL_USER         = os.getenv("GMAIL_USER", "admin@pbdproject.org")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
DRAFT_RECIPIENT    = "research@pbdproject.org"

EXCLUDED_ATTENDEES = {
    "cyndi@thegoodlandgroupadvisors.com",
    "tiffanycleveland@letusainc.com",
    "eretana1@hotmail.com",
    "gepalacio59@gmail.com",
    "regina.zr@gmail.com",
}

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

PROMPT = """You are drafting a post-call follow-up email on behalf of Andrew Longenecker, CEO of PBD Project (a nonprofit focused on Peroxisomal Biogenesis Disorders).

Andrew attended this meeting. You did not.
Write ONLY in Andrew's voice — warm, professional, concise, and human.

Follow this exact structure:
1. Greeting: recipient's first name followed by a dash (e.g. "Hi John -")
2. One genuine sentence thanking them for their time
3. 2-3 sentences on the most important topics or takeaways
4. Action items or next steps if any (skip if none)
5. Sign off with exactly:
Thanks again.
Andrew

Rules:
- Under 200 words
- No subject line in the body
- Nothing after "Andrew"

Also provide:
- Recipient's email address if found in the transcript (or write "unknown")
- A short subject line

Respond in exactly this format:
RECIPIENT_EMAIL: [email or unknown]
SUBJECT: [subject line]
BODY:
[email body only]

---
TRANSCRIPT:
{transcript}"""


def draft_email(transcript_text: str, otter_url: str = ""):
    # Check exclusions
    for email in EXCLUDED_ATTENDEES:
        if email.lower() in transcript_text.lower():
            print(f"SKIPPED — excluded attendee found: {email}")
            return

    print("Drafting with Gemini...")
    response = gemini_client.models.generate_content(
        model="gemini-1.5-flash",
        contents=PROMPT.format(transcript=transcript_text[:8000]),
    )
    raw = response.text.strip()

    # Parse
    recipient_email = "unknown"
    subject = "Post-Call Follow-Up"
    body = ""
    lines = raw.split("\n")
    body_start = 0

    for i, line in enumerate(lines):
        if line.upper().startswith("RECIPIENT_EMAIL:"):
            recipient_email = line.split(":", 1)[1].strip()
        elif line.upper().startswith("SUBJECT:"):
            subject = line.split(":", 1)[1].strip()
        elif line.upper().startswith("BODY:"):
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]).strip()

    print(f"\n{'─'*60}")
    print(f"OTTER:   {otter_url}")
    print(f"TO:      {recipient_email}")
    print(f"SUBJECT: {subject}")
    print(f"{'─'*60}")
    print(body)
    print(f"{'─'*60}\n")

    return recipient_email, subject, body, otter_url


def send_email(recipient_email, subject, body, otter_url):
    email_content = f"""{otter_url}

{recipient_email}

{subject}

{body}"""

    msg = MIMEMultipart()
    msg["Subject"] = f"[POST-CALL DRAFT] {subject}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = DRAFT_RECIPIENT
    msg.attach(MIMEText(email_content, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, DRAFT_RECIPIENT, msg.as_string())

    print(f"Sent to {DRAFT_RECIPIENT}")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--test" in args
    files = [a for a in args if not a.startswith("--")]

    if not files:
        print("Usage: python3 pilot_manual.py transcript1.txt [--test]")
        sys.exit(1)

    for filepath in files:
        print(f"\nProcessing: {filepath}")
        print("─" * 60)

        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue

        with open(filepath) as f:
            transcript_text = f.read().strip()

        if not transcript_text or "PASTE TRANSCRIPT" in transcript_text:
            print("No transcript found in file. Please paste the transcript text.")
            continue

        # Get otter URL from filename or first line
        otter_url = ""
        first_line = transcript_text.split("\n")[0]
        if first_line.startswith("http"):
            otter_url = first_line
            transcript_text = "\n".join(transcript_text.split("\n")[1:]).strip()

        result = draft_email(transcript_text, otter_url)
        if result and not dry_run:
            send_email(*result)
        elif dry_run:
            print("DRY RUN — not sent.")
