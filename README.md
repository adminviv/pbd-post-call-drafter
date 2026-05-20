# PBD Project — Post-Call Email Drafter

Automatically drafts follow-up emails after your Otter.ai meetings and sends them to your inbox for review.

**Built by:** Genevieve (VA)
**Sends to:** research@pbdproject.org
**Schedule:** Every weekday at 2:00 AM Eastern Time

---

## What It Does

Every weekday morning at 2am ET, the tool:

1. Logs into your Otter.ai account and scans for recent meetings
2. Skips internal calls (standups, personal, family)
3. Drafts a follow-up email in your voice for each external meeting
4. Sends the draft to **research@pbdproject.org** for your review
5. You copy, edit if needed, and send from your own email

The email drafts arrive with:
- The Otter link for reference
- Recipient email address
- Subject line
- Full email body in your writing style

---

## ⏸ How to PAUSE (e.g. if you're traveling)

**To stop all drafts from being sent:**

1. Open the project folder: `post_call_drafter`
2. Create a new empty file named exactly: **`PAUSED`** (no extension)
3. That's it — the tool will see that file and skip everything

> On Mac: open the folder in Finder → right-click → New File → name it `PAUSED`

**To resume when you're back:**

1. Delete the `PAUSED` file from the folder
2. The next scheduled run will proceed normally

---

## 📁 Project Folder Contents

| File | Purpose |
|------|---------|
| `auto_drafter.py` | Main script — runs the full pipeline |
| `draft_email.py` | AI email drafting logic + prompt |
| `otter_client.py` | Logs into Otter.ai and extracts transcripts |
| `otter_session.json` | Your Otter.ai login cookies (needs refresh every ~3 months) |
| `.env` | API keys and passwords (never share this file) |
| `processed_urls.log` | Log of meetings already drafted (prevents duplicates) |
| `cron.log` | Log of every automated run — check here if something looks off |
| `PAUSED` | Create this file to pause the tool. Delete it to resume. |

---

## ▶️ How to Run Manually

Open Terminal, then:

```bash
cd /Users/mba/Documents/post_call_drafter

# Draft emails for all recent meetings (since last Friday):
python3 auto_drafter.py --auto

# Draft for a specific Otter link:
python3 auto_drafter.py https://otter.ai/u/XXXX

# Preview without sending (dry run):
python3 auto_drafter.py --auto --test
```

---

## 🔄 Meetings That Are Automatically Skipped

The tool never drafts emails for:

- Any meeting with these keywords in the title: `standup`, `stand-up`, `family`, `personal`, `internal`, `genevieve`, `gen espra`
- Any meeting where Genevieve or other internal team members are the only attendees
- Meetings with no transcript (not recorded, or Otter failed to load)

---

## 🔑 When Otter Cookies Expire (~every 3 months)

If emails suddenly stop arriving, the Otter login session likely expired. To fix:

1. Open **Chrome** and log into otter.ai
2. Install the **Cookie-Editor** Chrome extension
3. On otter.ai, click the Cookie-Editor icon → **Export All** → Copy
4. Open `otter_session.json` in the project folder
5. Replace the entire contents with the copied cookies
6. Save the file

The tool will work again immediately on the next run.

---

## 📋 Checking the Logs

To see what ran and when:

```bash
cat /Users/mba/Documents/post_call_drafter/cron.log
```

Each run shows: which meetings were found, which were skipped, what was drafted, and whether the email was sent successfully.

---

## ❓ Troubleshooting

| Problem | Fix |
|---------|-----|
| No emails arriving | Check `cron.log` — likely Otter cookies expired |
| Email says "EMAIL NOT FOUND" | Andrew needs to fill in the recipient manually |
| Duplicate emails | Won't happen — `processed_urls.log` prevents re-sending |
| Wrong tone/content | Forward the bad example to Genevieve to improve the AI prompt |
| Want to add a contact to the skip list | Ask Genevieve to add their email to `EXCLUDED_ATTENDEES` in `draft_email.py` |

---

## 🛑 How to Stop Permanently

To completely disable the automation:

```bash
crontab -r
```

To re-enable it:

```bash
cd /Users/mba/Documents/post_call_drafter
python3 -c "
import subprocess
entry = 'TZ=America/New_York\n0 2 * * 1-5 cd /Users/mba/Documents/post_call_drafter && /usr/bin/python3 auto_drafter.py --auto >> /Users/mba/Documents/post_call_drafter/cron.log 2>&1'
subprocess.run('(crontab -l 2>/dev/null; echo \"' + entry + '\") | crontab -', shell=True)
print('Cron restored.')
"
```

---

*Questions? Contact Genevieve.*
