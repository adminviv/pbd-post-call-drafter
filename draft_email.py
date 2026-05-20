#!/usr/bin/env python3
"""
Post-Call Email Drafter
-----------------------
Fetches an Otter.ai transcript, drafts a follow-up email in Andrew's voice,
and sends the draft to research@pbdproject.org (Andrew's work email).

Usage:
  python draft_email.py                          # processes latest transcript
  python draft_email.py <otter_share_url>        # processes specific transcript
  python draft_email.py --test                   # dry run, prints draft only
"""

import os
import re
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from groq import Groq
from otter_client import get_session, get_transcript_from_share_url, get_latest_transcript

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
OTTER_EMAIL        = os.getenv("OTTER_EMAIL")
OTTER_PASSWORD     = os.getenv("OTTER_PASSWORD")
GMAIL_USER         = os.getenv("GMAIL_USER", "admin@pbdproject.org")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
DRAFT_RECIPIENT    = "research@pbdproject.org"  # Andrew's work email

# Emails — if ANY of these are attendees, skip the draft entirely
EXCLUDED_ATTENDEES = {
    # Internal / personal
    "genevieve.espra.work@gmail.com",
    "genevieve@pbdproject.org",
    # External excluded contacts
    "cyndi@thegoodlandgroupadvisors.com",
    "tiffanycleveland@letusainc.com",
    "eretana1@hotmail.com",
    "gepalacio59@gmail.com",
    "regina.zr@gmail.com",
}

# Meeting title keywords — if ANY appear in the title, skip the draft
EXCLUDED_TITLE_KEYWORDS = {
    "standup", "stand-up", "stand up",
    "family", "personal", "internal",
    "genevieve", "gen espra",
}

# ── Groq setup ──────────────────────────────────────────────────────────────
groq_client = Groq(api_key=GROQ_API_KEY)

# ── Otter transcript corrections ────────────────────────────────────────────
# Otter mishears PBD Project terminology. Fix before sending to AI.
OTTER_CORRECTIONS = [
    # ── Peroxisome misspellings ───────────────────────────────────────────
    (r"\bperox zone\b",              "peroxisome"),
    (r"\bperoxo\b",                  "peroxisome"),
    (r"\bperox\b",                   "peroxisome"),
    (r"\bperoxy some\b",             "peroxisome"),
    (r"\bperoxy\b",                  "peroxisome"),
    (r"\bperox is some\b",           "peroxisome"),
    (r"\bper oxisome\b",             "peroxisome"),

    # ── PEX gene names (PEX1–PEX26) ─────────────────────────────────────
    (r"\bpex\s+(\d+)\b",             r"PEX\1"),
    (r"\bp\s*e\s*x\s*(\d+)\b",       r"PEX\1"),

    # ── Disease names ────────────────────────────────────────────────────
    (r"\bPBD's\b",                   "PBDs"),
    (r"\bzel[lw]+eger\b",            "Zellweger"),
    (r"\bzel weger\b",               "Zellweger"),
    (r"\bzell weger\b",              "Zellweger"),
    (r"\bNALD\b",                    "Neonatal Adrenoleukodystrophy (NALD)"),
    (r"\bneonatal adrenol\w+\b",     "Neonatal Adrenoleukodystrophy (NALD)"),
    (r"\bIRD\b",                     "Infantile Refsum Disease (IRD)"),
    (r"\brefsum\b",                  "Refsum"),
    (r"\badrenol[ue]+kodystrophy\b", "Adrenoleukodystrophy"),
    (r"\bALD\b",                     "Adrenoleukodystrophy (ALD)"),

    # ── Biological mechanisms / metabolites ──────────────────────────────
    (r"\bplasmid a\b",               "plasmalogen"),
    (r"\bplasm alogen\b",            "plasmalogen"),
    (r"\bplasma logen\b",            "plasmalogen"),
    (r"\bplasmalog\w+\b",            "plasmalogen"),
    (r"\bVLCFA\b",                   "very long chain fatty acids (VLCFAs)"),
    (r"\bvery long chain fatty acid\b", "very long chain fatty acid (VLCFA)"),
    (r"\bROS\b",                     "reactive oxygen species (ROS)"),
    (r"\bredox home[os]+tasis\b",    "redox homeostasis"),
    (r"\bfar[tn]+esyl\b",            "farnesyl"),
    (r"\bphi tanic\b",               "phytanic"),
    (r"\bphytol\b",                  "phytol"),
    (r"\bperox i somal\b",           "peroxisomal"),

    # ── PBD Project tools & research ─────────────────────────────────────
    (r"\bperox[iy]\s*spy\b",         "PeroxiSPY"),
    (r"\bperox[iy]\s*os\b",          "PeroxiOS"),
    (r"\bhigh throughput screen\w*\b", "high-throughput screening (HTS)"),
    (r"\bHTS\b",                     "high-throughput screening (HTS)"),

    # ── Partner/program names ─────────────────────────────────────────────
    (r"\brares\s+one\b",             "Rare As One"),
    (r"\brare\s+as\s+1\b",           "Rare As One"),
    (r"\bfaster\s+cures\b",          "FasterCures"),
    (r"\bmilken\s+inst\w*\b",        "Milken Institute"),
    (r"\bterr[ae][iy]\b",            "Terray"),
]


def clean_transcript(text):
    """Fix known Otter transcription errors for PBD Project terminology."""
    for pattern, replacement in OTTER_CORRECTIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ── Prompt ──────────────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """You are drafting a post-call follow-up email on behalf of Andrew Longenecker, CEO of PBD Project.

════════════════════════════════════════════════════════
WHO ANDREW IS — read this carefully before writing anything
════════════════════════════════════════════════════════

Andrew Longenecker is the founder and CEO of PBD Project, a nonprofit research accelerator and biotech incubator. His son Diego was diagnosed with a rare Peroxisomal Biogenesis Disorder (PBD) at 24 months. Andrew launched a patient advocacy group, then expanded the mission to reveal the peroxisome's vast potential for all of medicine — not just rare disease.

THE PEROXISOME:
- Present in every cell of the human body
- Functions: cleans up cellular toxins, breaks down lipids into consumable parts, monitors oxidative risks
- Implicated in: ALS, cancer, Alzheimer's, multiple sclerosis, aging, metabolic diseases, viral infections, Peroxisomal Biogenesis Disorders
- Critically underfunded: $8.4M / 36 NIH projects (2015–2024) vs. $1.9B / 5,327 projects for mitochondria
- Andrew's analogy: peroxisomes are where mitochondria were decades ago — no widely adopted dyes, no clean proliferators/inhibitors, very limited HTS-ready assays

PBD PROJECT'S APPROACH (venture-style):
- Incubate Solutions: launch promising research programs with shared tools, data platforms, strategic guidance
- Cultivate Ecosystems: unite scientists, labs, patient communities around translational priorities
- Unlock Capital: attract, deploy, and multiply funding across sectors

RESEARCH NETWORK (35+ global PIs):
Harvard, Johns Hopkins, Imperial College London, UC Berkeley, University of Toronto, University of Pittsburgh, McGill, USC, University of Queensland, Bar-Ilan University, Weizmann Institute of Science, University of Amsterdam, KU Leuven, University of Alberta, Albert-Ludwigs-Universität Freiburg, + more

KEY TECHNICAL TERMINOLOGY (always spell these correctly):
- Peroxins: PEX1, PEX2, PEX3, PEX5, PEX6, PEX7, PEX10, PEX12, PEX13, PEX14, PEX16, PEX19, PEX26
- Diseases: Zellweger Syndrome, Neonatal Adrenoleukodystrophy (NALD), Infantile Refsum Disease (IRD), Adrenoleukodystrophy (ALD), Peroxisomal Biogenesis Disorders (PBDs)
- Mechanisms: very long chain fatty acids (VLCFAs), plasmalogens, bile acid biosynthesis, reactive oxygen species (ROS), redox homeostasis, fatty acid oxidation (FAO), lipid metabolism, phytanic acid
- PBD Project tools: PeroxiSPY (peroxisome reporter tool by Triana Amen), PeroxiOS (peroxisome literature navigator), PEX10 brain organoid (built by Ernst J. Wolvetang — first brain organoid for peroxisomal disease)
- Partners: FasterCures (Milken Institute), Terray Therapeutics (large HTS screening platform, pro bono partner), Rare As One program

ANDREW'S POSITIONING:
- He is ALWAYS the expert and the one sharing/pitching the mission — never the student learning about the peroxisome
- He is genuinely excited and grateful to everyone he meets
- He frames the opportunity broadly: "peroxisome as nodal mechanism" connecting cancer, neurodegeneration, metabolism — not just rare disease
- He often references the funding gap ($8.4M vs $1.9B for mitochondria) to convey urgency

════════════════════════════════════════════════════════
ANDREW'S REAL EMAILS — study these carefully. Your draft must match this voice exactly.
════════════════════════════════════════════════════════

--- EXAMPLE 1: Short, intro-focused ---
RECIPIENT_EMAIL: michal.preminger@gmail.com
SUBJECT: PBD Project thank you and peroxisome visibility follow-up
BODY:
Michal - thank you for the great discussion last week!

I really loved your ideas on how to increase visibility for the peroxisome (e.g., symposium, bringing on influential figures, learning from the ALS experience) and looking forward to pushing these forward.

I really appreciate your offer to introduce me to Vanessa Barth, Michael Weingarten, and Oliver Dodd - I sent a separate email for easy forwarding if that works for you.

Thank you very much!
Andrew

--- EXAMPLE 2: Specific follow-up ask ---
RECIPIENT_EMAIL: ulrich.stilz@web.de
SUBJECT: PBD Project thank you and CSO search follow-up
BODY:
Uli - thanks again for the great discussion about our CSO search.

Your insights on the right backgrounds for this role really resonated with me and I can't thank you enough for taking the time. I also loved your ideas for sourcing potential candidates (e.g., LI post, monitoring LI and Endpoint News, consider starting with advisors).

Thanks also for mentioning Christine Ivashenko - I will reach out to her now.

I spent some time after our call drafting a JD - any chance you might be open to taking a quick look and providing feedback? (no worries if you don't have capacity)

Thanks again.
Andrew

--- EXAMPLE 3: Strategic / fundraising discussion ---
RECIPIENT_EMAIL: rwolfert@thehartwellfoundation.org
SUBJECT: PBD Project thank you and Hartwell Foundation follow-up
BODY:
Bob - thank you for taking the time this morning! Super helpful conversation and I appreciated your candor and generosity with your perspective.

I love the idea of engaging with Centers of Excellence and starting conversations through development offices at major institutions vs. seeking out individual researchers directly. I think this can really help our efforts re: building momentum in the peroxisome space.

Thanks also for offering to keep an eye out for anyone working in research topics connected to the peroxisome who might be a fit for us!

On our end, as we build out our research network, I'd love to connect you with early-career, innovative researchers that Hartwell tends to back.

Really grateful for Roarke's introduction and looking forward to staying in touch as the PBD Project evolves. I'll make sure to keep you posted on our progress.

Thank you
Andrew

--- EXAMPLE 4: Technical / complex discussion with numbered follow-ups ---
RECIPIENT_EMAIL: dhriti@example.com
SUBJECT: PBD Project thank you and peroxisome assay collaboration follow-up
BODY:
Dhriti - really enjoyed our conversation today! Thank you for the time and excited to have you involved.

Summarizing the two workstreams we discussed, how does the below sound?

1) Tactical assay adaptation: Utilizing your experience with mitochondrial assays, identify specific assays that could be adapted for peroxisome biology and made HTS-compatible (e.g., lipid oxidation kits as a promising starting point). Objective is to identify concrete near-term projects that would be immediately useful to anyone interested in running a peroxisome-based screen.

2) Peroxisome tools landscape + translation strategy: Broader literature review to map what technologies currently exist for studying peroxisome biology, identify the key research gaps, and think through what the field needs over the next 2-5 years to push toward translation.

Additional follow-ups mentioned during call:
- Triana Amen developed PeroxiSPY, a close collaborator of ours
- Ernst J. Wolvetang built our PEX10 brain organoid (which we believe is the first brain organoid for peroxisomal disease!) so he could be a useful resource
- Terray Therapeutics: large screening platform, who has offered a pro bono effort to do work for us if we can hand them a clear target

Let me know if any questions! Really looking forward to diving into this.

Thanks again,
Andrew

--- EXAMPLE 5: Biotech / diligence ---
RECIPIENT_EMAIL: christy@hatterasvp.com
SUBJECT: PBD Project thanks and peroxisome biotech vetting follow-up
BODY:
Christy - thank you for the great discussion last week!

I really loved your ideas on helping to vet the peroxisome biotech we discussed (e.g., Judith Li, Derek Yoon) as well as learning from my existing network (particularly asking Josh Sommer what he would do differently if he had it to do over again!)

I would be curious in your discussions with Hatteras colleagues (I believe you mentioned Ben Scruggs and Kseniya Simpson?) if you have any records in your historical diligence of any assets related to the peroxisome. Obviously, any assets that specifically mention the peroxisome would be very interesting, but also related mechanisms as well (e.g., fatty acid oxidation, plasmalogen or bile acid biosynthesis, reactive oxygen species / ROS / redox homeostasis, lipid metabolism).

Thank you very much!
Andrew

════════════════════════════════════════════════════════
RULES — follow these precisely
════════════════════════════════════════════════════════

GREETING FORMAT:
- Write "FirstName - opening sentence" ALL ON ONE LINE — do NOT put the name on its own line followed by a blank line.
- Correct:   "Michal - thank you for the great discussion last week!"
- Wrong:     "Michal -\n\nThank you for the great discussion last week!"

SPECIFICITY IS EVERYTHING:
- Every sentence must contain a real detail pulled from this transcript. Zero generic filler.
- BAD: "Your suggestion to reach out to the Development Office was helpful."
- GOOD: "I loved your idea of approaching development offices at Centers of Excellence vs. reaching out to individual researchers directly."
- BAD: "Thanks for mentioning Dan and Imran."
- GOOD: "Thanks for mentioning Dan Haber and Imran Khan — I'll reach out to both this week."

PARENTHETICAL STYLE:
- Use "(e.g., X, Y, Z)" when listing ideas, examples, or names — exactly as Andrew does.
- Every email should contain at least one parenthetical list pulled from the transcript.

NAMES — scan the ENTIRE transcript:
- Pull every full name mentioned: introductions offered, candidates, collaborators, contacts.
- Use FIRST AND LAST NAME whenever possible.

FORMAT ADAPTS TO MEETING COMPLEXITY:
- Short meeting or simple follow-up → 2-3 short paragraphs (like Michal or Bob)
- Technical or complex discussion with multiple follow-ups → use numbered list or bullets (like Dhriti or Jillian)
- Let the content of the meeting drive the format, not a template.

OPENER — vary naturally, never repeat the same one:
- "FirstName - thank you for the great discussion last week!"
- "FirstName - thanks again for the great conversation about [specific topic]."
- "FirstName - really enjoyed our conversation today!"
- "FirstName - thank you for taking the time [today/this morning/last week]!"

SIGN-OFF — vary naturally:
- "Thanks again.\nAndrew"
- "Thank you very much!\nAndrew"
- "Thank you\nAndrew"
- "Thanks again,\nAndrew"
- "Really looking forward to [specific next step] — thanks again\nAndrew"

ACTION ITEMS — be concrete:
- BAD: "I will follow up with you soon."
- GOOD: "I'll send over the one-pager we discussed by end of week."
- BAD: "I will definitely keep you posted."
- GOOD: "I'll make sure to keep you posted as we finalize the CSO hire."

BANNED PHRASES — never write these:
- "Your suggestion was particularly helpful"
- "I appreciated your offer to help"
- "I appreciate the connection"
- "I valued your insights"
- "navigate the process"
- "I'm grateful for your willingness"
- "looking forward to our continued collaboration"
- "I will reach out to you"
- "I appreciate your time and consideration"
- Any phrase that could fit in ANY email regardless of what was discussed

SUBJECT LINE:
- Must include "PBD Project" + specific topic of this meeting.
- BAD: "PBD Project thank you and follow-up"
- GOOD: "PBD Project thank you and CSO search follow-up"
- GOOD: "PBD Project thanks and Hartwell Foundation intro"
- GOOD: "PBD Project thank you and newsletter strategy follow-up"

OTHER:
- Under 200 words (unless the meeting was complex/technical with many follow-ups — then go up to 300)
- Andrew never explains the peroxisome as if the other person doesn't know what it is
- Recipient email: use the attendee list. Each entry shows the full email AND a "username hint" (the prefix before @). Match the person you're writing to against the username hint — e.g., "astratton" = Andra Stratton → astratton@biohub.org, "rpuerini" = Raymond Puerini → rpuerini@milkeninstitute.org, "rwolfert" = Bob Wolfert → rwolfert@thehartwellfoundation.org. If still no match after trying, write [EMAIL NOT FOUND — fill in: Full Name]
- Do NOT write anything after "Andrew"

TECHNICAL ACCURACY — before finalizing, verify every technical term:
- Gene/protein names: PEX genes are always capitalized and hyphen-free (PEX1 not Pex-1 or pex1)
- Disease names: Zellweger Syndrome (not Zellweger's), NALD, IRD, ALD, PBD — always capitalize
- Mechanisms: plasmalogen (not plasmalog or plasmid), VLCFA (not VLCFA's unless plural context), ROS
- Tools: PeroxiSPY (capital S, capital PY), PeroxiOS (capital OS)
- Institutions: spell out fully if mentioned (e.g., Milken Institute, not Milken Inst.)
- If the transcript mentions a name or term you are unsure about, use the exact spelling from the KEY TECHNICAL TERMINOLOGY list above rather than guessing

---

Meeting title: {title}
Date: {date}

Attendees:
{attendees}

Action items noted by Otter:
{action_items}

Full transcript:
{transcript}

---

Respond in EXACTLY this format:
RECIPIENT_EMAIL: [email address, or "[EMAIL NOT FOUND — fill in: Full Name]"]
SUBJECT: [subject line including "PBD Project"]
BODY:
[email body — "FirstName - opening sentence on same line"]"""


def check_exclusions(speakers, title=""):
    """Return a reason string if this meeting should be skipped, else None."""
    # Check attendee email list
    for s in speakers:
        email = (s.get("email") or "").lower()
        if email in EXCLUDED_ATTENDEES:
            return f"excluded attendee: {email}"

    # Check meeting title keywords
    title_lower = title.lower()
    for kw in EXCLUDED_TITLE_KEYWORDS:
        if kw in title_lower:
            return f"excluded title keyword: '{kw}'"

    return None


# If a meeting has more than this many external attendees, treat as a group call
# and generate individual follow-up emails for EACH attendee.
GROUP_CALL_THRESHOLD = 3

# Emails that belong to Andrew / PBD Project — never draft TO these
ANDREW_EMAILS = {
    "andrew.longenecker@gmail.com",
    "andrew@pbdproject.org",
    "research@pbdproject.org",
    "admin@pbdproject.org",
}


def _call_groq(prompt):
    """Makes one Groq API call with model fallback. Returns raw response text."""
    MODELS = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "deepseek-r1-distill-llama-70b",
        "qwen-qwq-32b",
    ]
    for model in MODELS:
        try:
            resp = groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.6,
            )
            if model != MODELS[0]:
                print(f"  (using fallback model: {model})")
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e).lower()
            if any(x in err for x in ["rate_limit", "429", "413", "decommissioned",
                                       "model_not_found", "request too large"]):
                print(f"  Skipping {model}: {str(e)[:80]}")
                continue
            raise
    raise Exception(
        "All Groq models are rate limited. "
        "Daily limits reset every 24 hours — try again tomorrow."
    )


def _normalize_signoff(body):
    """Strip any sign-off region from body and append one clean sign-off."""
    body = body.rstrip()
    lines = body.split('\n')

    SIGNOFF_PREFIXES = (
        "thanks",
        "thank you",
        "andrew",
        "excited to see",
        "really looking forward",
        "looking forward to seeing",
        "looking forward to speaking",
    )

    i = len(lines) - 1
    while i >= 0:
        stripped = lines[i].strip().lower()
        if stripped == '' or any(stripped.startswith(p) for p in SIGNOFF_PREFIXES):
            i -= 1
        else:
            break

    return '\n'.join(lines[:i + 1]).rstrip() + "\n\nThanks again.\nAndrew"


def _parse_groq_response(raw):
    """Parse Groq output into (recipient_email, subject, body)."""
    recipient_email = "[EMAIL NOT FOUND — fill in]"
    subject = "PBD Project thank you and follow-up"
    body = raw

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

    body_lines = lines[body_start:]
    cleaned = []
    for line in body_lines:
        upper = line.upper().strip()
        # Strip leaked header lines
        if upper.startswith("RECIPIENT_EMAIL:") or upper.startswith("SUBJECT:"):
            continue
        # Strip bare email addresses that leaked into the body (e.g. "rwolfert@...")
        stripped = line.strip()
        if re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', stripped):
            continue
        cleaned.append(line)

    body = "\n".join(cleaned).strip()
    body = _normalize_signoff(body)
    return recipient_email, subject, body


def _build_prompt(transcript_data, recipient_hint=""):
    """Build the Groq prompt for a given transcript. recipient_hint narrows who to write to."""
    attendees = "\n".join(
        f"- {s['email']}  (username hint: '{s['name']}')"
        for s in transcript_data['speakers']
    ) or "- Not listed"

    action_items = "\n".join(
        f"- {a}" for a in transcript_data['action_items']
    ) or "- None detected"

    raw_t = transcript_data['transcript']
    if len(raw_t) > 50000:
        sampled = raw_t[:38000] + "\n\n[...middle omitted...]\n\n" + raw_t[-12000:]
    else:
        sampled = raw_t
    cleaned_transcript = clean_transcript(sampled)

    prompt = PROMPT_TEMPLATE.format(
        title=transcript_data['title'],
        date=transcript_data['date'],
        attendees=attendees,
        action_items=action_items,
        transcript=cleaned_transcript,
    )

    if recipient_hint:
        prompt += f"\n\nIMPORTANT: Write this email specifically TO: {recipient_hint}"

    return prompt


def draft_email_with_groq(transcript_data):
    """Draft a single follow-up email. Returns (recipient_email, subject, body)."""
    prompt = _build_prompt(transcript_data)
    raw = _call_groq(prompt)
    return _parse_groq_response(raw)




def send_draft_email(
    recipient_email,
    subject,
    body,
    otter_url="",
    meeting_title="",
    speakers=None,
    to="",
):
    """
    Sends the formatted draft email.
    'to' overrides the default DRAFT_RECIPIENT (use for testing).
    'speakers' is the full attendee list — shown in the draft for group calls.
    """
    send_to = to if to else DRAFT_RECIPIENT

    # For group calls, list ALL attendee emails so Andrew sees everyone at once
    speakers = speakers or []
    external = [s["email"] for s in speakers if s["email"].lower() not in ANDREW_EMAILS]
    if len(external) > 1:
        all_emails_block = "ALL ATTENDEES:\n" + "\n".join(f"  {e}" for e in external)
    else:
        all_emails_block = recipient_email

    # Format exactly like Andrew's template
    email_content = (
        f"{otter_url}\n\n"
        f"{all_emails_block}\n\n"
        f"{subject}\n\n"
        f"{body}"
    )

    # Unique subject per meeting so each gets its own Gmail thread
    draft_subject = (
        f"[POST-CALL DRAFT] {meeting_title}"
        if meeting_title
        else f"[POST-CALL DRAFT] {subject}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = draft_subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = send_to

    msg.attach(MIMEText(email_content, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, send_to, msg.as_string())

    print(f"Draft sent to {send_to}")


def process(otter_url="", dry_run=False):
    # 1. Get Otter session
    session = get_session(OTTER_EMAIL, OTTER_PASSWORD)

    # 2. Fetch transcript
    if otter_url:
        data = get_transcript_from_share_url(session, otter_url)
    else:
        data = get_latest_transcript(session)

    print(f"Meeting: {data['title']}")
    print(f"Speakers: {[s['name'] for s in data['speakers']]}")

    # 3. Check exclusions (email + title)
    reason = check_exclusions(data["speakers"], title=data.get("title", ""))
    if reason:
        print(f"SKIPPED — {reason}")
        return

    # 4. Draft with Groq
    print("Drafting email with Groq...")
    recipient_email, subject, body = draft_email_with_groq(data)

    print(f"\n{'─'*60}")
    print(f"OTTER:     {otter_url}")
    print(f"TO:        {recipient_email}")
    print(f"SUBJECT:   {subject}")
    print(f"{'─'*60}")
    print(body)
    print(f"{'─'*60}\n")

    # 5. Send (or dry run)
    if dry_run:
        print("DRY RUN — email not sent.")
    else:
        send_draft_email(recipient_email, subject, body, otter_url, data['title'])


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--test" in args
    url = next((a for a in args if a.startswith("http")), "")
    process(otter_url=url, dry_run=dry_run)
