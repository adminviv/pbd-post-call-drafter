"""
Otter.ai client — uses Playwright headless browser to load transcripts.
Cookies from browser export are injected so no login is needed.
"""

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

COOKIE_FILE = Path(__file__).parent / "otter_session.json"
BASE = "https://otter.ai"


def _load_raw_cookies() -> list:
    """Load cookies from the browser export JSON file."""
    if not COOKIE_FILE.exists():
        raise Exception(f"Cookie file not found: {COOKIE_FILE}")
    with open(COOKIE_FILE) as f:
        cookies = json.load(f)
    # Playwright expects 'sameSite' as 'Strict'|'Lax'|'None' (capitalized)
    samesite_map = {"strict": "Strict", "lax": "Lax", "no_restriction": "None", None: "None"}
    cleaned = []
    for c in cookies:
        cleaned.append({
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"] if c["domain"].startswith(".") else c["domain"],
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": samesite_map.get(c.get("sameSite"), "None"),
        })
    return cleaned


def get_session(email: str, password: str):
    """Returns cookies list — Playwright sessions are created per-call."""
    cookies = _load_raw_cookies()
    print(f"Loaded {len(cookies)} cookies from browser export.")
    return cookies


def get_transcript_from_share_url(cookies: list, share_url: str) -> dict:
    """Use Playwright to load the Otter share page and extract transcript."""
    share_url = share_url.split("?")[0].rstrip("/")
    print(f"Opening: {share_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        # Go to the transcript page
        page.goto(share_url, wait_until="domcontentloaded", timeout=30000)

        # Wait for transcript text to appear
        try:
            page.wait_for_selector(
                "div.transcript-body, div[class*='transcript'], span[class*='transcript'], "
                ".speech-text, div[class*='speech'], .otter-transcript",
                timeout=15000
            )
        except PlaywrightTimeout:
            print("Transcript selector timed out, trying to extract anyway...")

        # Give JS extra time to render
        time.sleep(3)

        # Try to intercept API responses via page evaluation
        transcript_text = page.evaluate("""() => {
            // Try React fiber / Redux store
            const root = document.getElementById('root') || document.body;

            // Try to find transcript elements by common patterns
            const selectors = [
                '.transcript-body',
                '[class*="transcript"]',
                '[class*="speech-text"]',
                '[class*="speechText"]',
                '.MuiTypography-body1',
                'p[class*="text"]',
            ];

            let texts = [];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 3) {
                    els.forEach(el => {
                        const t = el.innerText?.trim();
                        if (t && t.length > 10) texts.push(t);
                    });
                    if (texts.length > 0) break;
                }
            }
            return texts.join('\\n');
        }""")

        # Get meeting title
        title = page.title() or "Meeting"
        title = title.replace(" - Otter.ai", "").replace("Otter Voice Meeting Notes", "").strip()

        # Get full page text as fallback
        if not transcript_text or len(transcript_text) < 100:
            print("Trying full page text extraction...")
            transcript_text = page.evaluate("""() => {
                // Remove nav, header, footer, buttons
                const noise = document.querySelectorAll('nav, header, footer, button, script, style');
                noise.forEach(el => el.remove());
                return document.body.innerText;
            }""")

        # ── Extract Otter action items from Summary tab ───────────────────
        action_items = []
        try:
            page.click("text=Summary", timeout=5000)
            time.sleep(2)
            ai_text = page.evaluate("""() => {
                const section = document.querySelector('[class*="action"], [data-testid*="action"]');
                return section ? section.innerText : '';
            }""")
            if ai_text:
                for line in ai_text.split('\n'):
                    line = line.strip()
                    if line and len(line) > 10 and not line.lower().startswith('action item'):
                        action_items.append(line)
            print(f"Otter action items: {action_items}")
        except Exception as e:
            print(f"Could not extract action items: {e}")

        # ── Extract attendee emails via Share dialog ──────────────────────
        attendee_emails = []
        import re as _re

        def _try_extract_emails():
            """Click Share, optionally reveal calendar guests, scrape emails."""
            page.evaluate("() => window.scrollTo(0, 0)")
            time.sleep(1)
            # Try normal click first, fall back to JS click
            try:
                page.click("[data-testid='share-button']", timeout=8000, no_wait_after=True)
            except Exception:
                page.evaluate("() => document.querySelector('[data-testid=\"share-button\"]')?.click()")
            time.sleep(3)
            # Reveal calendar guests if button exists
            try:
                page.click("text=calendar guest", timeout=3000, no_wait_after=True)
                time.sleep(2)
            except Exception:
                pass
            dialog_text = page.evaluate("() => document.body.innerText")
            found = _re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', dialog_text)
            skip = {"otter.ai", "cdn", "sentry", "w3.org", "schema.org", "apple.com", "google.com"}
            emails = list({e for e in found if not any(s in e.lower() for s in skip)})
            emails = [e for e in emails if "andrew.longenecker" not in e.lower()]
            return emails

        # Retry up to 2 times — share button click is occasionally blocked
        for attempt in range(2):
            try:
                attendee_emails = _try_extract_emails()
                if attendee_emails:
                    break
                print(f"  Share dialog attempt {attempt+1}: no emails found, retrying...")
                time.sleep(2)
            except Exception as e:
                print(f"  Share dialog attempt {attempt+1} failed: {e}")
                time.sleep(2)

        print(f"Attendee emails: {attendee_emails}")

        browser.close()

    if not transcript_text or len(transcript_text) < 50:
        raise Exception(f"Could not extract transcript from {share_url}")

    print(f"Extracted {len(transcript_text)} characters of transcript.")

    # Build speakers list from attendee emails
    speakers = [{"name": e.split("@")[0], "email": e} for e in attendee_emails]

    return {
        "title": title or "Meeting",
        "date": "",
        "transcript": transcript_text,
        "action_items": action_items,
        "speakers": speakers,
    }


def _parse_date_hint(text, today):
    """
    Try to extract a date from Otter's home page listing text.
    Returns a datetime or None if unparseable.
    """
    t = text.lower()

    if "today" in t:
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)

    # Named weekdays: "Monday", "Friday", etc.
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, name in enumerate(day_names):
        if name in t:
            days_ago = (today.weekday() - i) % 7
            if days_ago == 0:
                days_ago = 7
            return today - timedelta(days=days_ago)

    # Month + day: "May 15", "Apr 3", etc.
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    for abbr, num in months.items():
        m = re.search(abbr + r"[a-z]*\.?\s+(\d{1,2})", t)
        if m:
            day = int(m.group(1))
            try:
                d = datetime(today.year, num, day)
                if d > today:
                    d = datetime(today.year - 1, num, day)
                return d
            except ValueError:
                pass

    return None


def get_transcripts_since(cookies, since_date):
    """
    Return a list of Otter transcript URLs for meetings on or after since_date.
    Loads the authenticated home page and scrapes the meeting list.
    """
    print(f"Scanning Otter home for meetings since {since_date.strftime('%A, %b %d %Y')}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        page.goto(f"{BASE}/home", wait_until="domcontentloaded", timeout=30000)

        # Wait for React to render — poll until links appear or timeout
        js_links = """() => document.querySelectorAll('a[href*="/u/"]').length"""
        for _ in range(20):          # up to 20 x 1.5s = 30s
            time.sleep(1.5)
            count = page.evaluate(js_links)
            if count > 0:
                break

        items = page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            document.querySelectorAll('a').forEach(link => {
                const href = link.href || '';
                if (!href.includes('/u/') || seen.has(href)) return;
                seen.add(href);
                let el = link;
                let text = '';
                for (let i = 0; i < 8; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    const t = el.innerText || '';
                    if (t.length > 10) { text = t.slice(0, 300); break; }
                }
                results.push({ href, title: (link.innerText || '').trim(), text });
            });
            return results;
        }""")

        browser.close()

    if not items:
        raise Exception(
            "Could not load Otter home page meetings. "
            "Try re-exporting cookies from Chrome (Cookie-Editor extension)."
        )

    today = datetime.now()
    urls = []
    seen = set()

    for item in items:
        href  = item.get("href", "")
        text  = item.get("text", "")
        title = item.get("title", "")

        if not href or href in seen:
            continue
        seen.add(href)

        meeting_date = _parse_date_hint(text, today)

        # Skip only when we're confident the meeting is before the cutoff
        if meeting_date is not None and meeting_date.date() < since_date.date():
            print(f"  Skipping (too old: {meeting_date.strftime('%b %d')}): {title or href}")
            continue

        url = href if href.startswith("http") else f"{BASE}{href}"
        date_str = meeting_date.strftime("%b %d") if meeting_date else "recent"
        print(f"  Queued ({date_str}): {title or url}")
        urls.append(url)

    return urls


def get_latest_transcript(cookies: list) -> dict:
    """Get the most recent transcript from Otter home page."""
    print("Opening Otter home to find latest transcript...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        page.goto(f"{BASE}/home", wait_until="domcontentloaded", timeout=30000)

        try:
            page.wait_for_selector("a[href*='/u/']", timeout=15000)
        except PlaywrightTimeout:
            browser.close()
            raise Exception("Could not load Otter home page.")

        # Click first transcript
        first_link = page.query_selector("a[href*='/u/']")
        if not first_link:
            browser.close()
            raise Exception("No transcripts found on Otter home page.")

        href = first_link.get_attribute("href")
        share_url = f"{BASE}{href}" if href.startswith("/") else href
        browser.close()

    return get_transcript_from_share_url(cookies, share_url)
