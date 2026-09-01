import json
import os
import re
import urllib.error
import urllib.request
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import AiStoredPair

STOP = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "is", "are",
    "how", "what", "when", "where", "why", "do", "does", "can", "i", "my",
    "me", "you", "your", "with", "about", "please", "tell",
}

SEED_QA = [
    (
        "What is Build Forces?",
        "Build Forces is America's construction workforce platform. You train, get certified, then find public work jobs and connect with companies. The top menu has Home, Training, Jobs, Portals, and Resources.",
    ),
    (
        "What is on the home page?",
        "Home is the landing page. Tap Get Started Free to choose a portal, or Explore Platform to see workers, instructors, homeowners, and companies. You can also call me at 415-555-0148.",
    ),
    (
        "What is under Training?",
        "Training has All courses, Safety training for OSHA and first aid, Equipment for excavator, loader, and forklift, and Concrete for forms, rebar, and finishing. Open Training in the top bar, then pick a path.",
    ),
    (
        "How do I start training?",
        "Tap Training, then All courses, or Get Started Free and create a Build Forces profile. After you sign in, My courses is where lessons and certificates live.",
    ),
    (
        "What is OSHA 10?",
        "OSHA 10 is a ten-hour construction safety class covering fall protection, PPE, electrical hazards, and jobsite awareness. A lot of public works jobs want it before you step on site. You will find safety courses under Training.",
    ),
    (
        "What PPE do I need?",
        "On most sites you will want a hard hat, safety glasses, a high-vis vest, gloves, and steel-toe or composite-toe boots. Extra gear like hearing protection or a harness depends on the task.",
    ),
    (
        "What is under Jobs?",
        "Jobs in the top bar has Find jobs for public works and crew openings, and Build resume for a verified profile companies trust. Sign in first if you want to apply.",
    ),
    (
        "How do I apply for a job?",
        "Go to Jobs, then Find jobs. Filter by trade and ZIP, open a posting, and apply. Keep your resume and certificates current so companies can hire you faster.",
    ),
    (
        "How do I build a resume?",
        "Open Jobs, then Build resume, or go to Resume after you sign in. Add trades, skills, and certificates so your profile looks ready for companies.",
    ),
    (
        "What are Portals?",
        "Portals is four doors. Build Forces is for crew careers. Instructors teach and issue certificates. Homeowners post home projects. Companies hire and run crews. Get Started Free opens the same choices.",
    ),
    (
        "How do workers sign in?",
        "Tap Log In at the top, or Portals, then Build Forces. New crew members use Get Started Free and Create profile. After login you see My courses, jobs, resume, messages, and AI call.",
    ),
    (
        "How do instructors use the site?",
        "Choose the Instructor portal. Instructors manage students, courses, assessments, and certificates. Register under Get Started Free, then open the instructor dashboard.",
    ),
    (
        "How do homeowners hire?",
        "Homeowners use Find Build Forces, Post a job, and My Projects. Sign in through the Homeowner portal. You can request quotes and hire verified crew.",
    ),
    (
        "How do companies hire?",
        "Companies use the Company portal for attendance, daily reports, tasks, payroll, labor sign-in, and safety. Sign in under Portals, then Company, or Get Started Free.",
    ),
    (
        "What is under Resources?",
        "Resources has How it works, Explore Platform, and Contact. How it works is train, certify, get hired. Contact is the form, phone, and office hours, Monday through Friday nine to six.",
    ),
    (
        "How do I contact you?",
        "You can keep talking with me on this line, 415-555-0148. Or open Resources, then Contact, and send a message. The team usually replies within one business day.",
    ),
    (
        "What is Get Started Free?",
        "Get Started Free in the header lets you pick a portal: crew, homeowner, instructor, or company. It is the fastest way to create the right account.",
    ),
    (
        "What is the worker journey?",
        "Three steps. Get training by completing safety and trade programs. Get certified with credentials companies trust. Then find public work jobs and connect with construction companies.",
    ),
    (
        "How do certificates work?",
        "Finish a course and you get a certificate with a verification code and QR. Companies scan it to confirm it is real. Certificates live under Training and your dashboard.",
    ),
    (
        "What is Explore Platform?",
        "Explore Platform shows all four communities: workers, instructors, homeowners, and companies. It is the outlined button on the home hero, and it is also under Resources.",
    ),
    (
        "How do I change language?",
        "Use the flag menu in the top right. The site supports English, Spanish, French, Russian, and Ukrainian.",
    ),
    (
        "What is a prevailing wage job?",
        "Prevailing wage jobs, often Davis-Bacon public works, pay a set rate plus fringe for that trade and county. Pay shows on the job posting.",
    ),
    (
        "How do I reset my password?",
        "On sign-in, tap Forgot password. We email a reset link if the account exists. Choose a new password with at least six characters.",
    ),
    (
        "Who is Maya?",
        "I am Maya, your Build Forces guide. I am here to walk you through training, jobs, portals, and getting started, in a calm, friendly call.",
    ),
    (
        "Hi hello hey",
        "Hi! I heard you. This is Maya. Tell me if you want training, jobs, portals, or help getting started.",
    ),
]


def tokens(text: str):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    greet_short = {"hi", "yo", "hey"}
    return {w for w in words if (len(w) > 1 or w in greet_short) and w not in STOP}


GREET_WORDS = {
    "hi", "hii", "hello", "hey", "howdy", "yo", "hiya", "there",
    "good", "morning", "afternoon", "evening",
}
GREET_FILLER = {"and", "just", "so", "please", "a", "the"}
HOWARE_WORDS = {
    "how", "are", "you", "doing", "going", "is", "it", "whats", "what",
    "up", "things", "today", "feeling",
}


def is_greeting(message: str) -> bool:
    words = re.findall(r"[a-z]+", (message or "").lower())
    if not words:
        return False
    if all(w in GREET_WORDS or w in GREET_FILLER for w in words):
        return True
    rest = [w for w in words if w not in GREET_WORDS and w not in GREET_FILLER]
    asks_how = "how" in words or "what" in words or "whats" in words
    return bool(rest) and asks_how and all(w in HOWARE_WORDS for w in rest)


def greeting_reply(message: str) -> str:
    words = set(re.findall(r"[a-z]+", (message or "").lower()))
    if words & {"how", "what", "whats"}:
        return (
            "I am doing great, thank you for asking. This is Maya with Build Forces. "
            "I can help with training, jobs, portals, or getting started. What would you like to do?"
        )
    return (
        "Hi! I heard you. This is Maya with Build Forces. "
        "I can help with training, jobs, portals, or getting started. What would you like to do?"
    )


GREET_REPLY = greeting_reply("hello")


def jaccard(a, b) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ensure_seed_pairs(db: Session) -> None:
    if not db.query(AiStoredPair).filter(AiStoredPair.source == "seed_v2").first():
        for question, answer in SEED_QA:
            db.add(AiStoredPair(question=question, answer=answer, source="seed_v2"))
        db.commit()
    greet_q = "Hi hello hey"
    if not db.query(AiStoredPair).filter(AiStoredPair.question == greet_q).first():
        db.add(
            AiStoredPair(
                question=greet_q,
                answer="Hi! I heard you. This is Maya. Tell me if you want training, jobs, portals, or help getting started.",
                source="seed_v2",
            )
        )
        db.commit()


PRONOUNS = {"that", "it", "this", "those", "them"}


def expand_query(message: str, history) -> str:
    words = set(re.findall(r"[a-z0-9]+", (message or "").lower()))
    if words & PRONOUNS:
        recent = " ".join(history[-2:]) if history else ""
        return "%s %s" % (message, recent[-400:])
    return message


def find_related(db: Session, query: str, limit: int = 3):
    ensure_seed_pairs(db)
    qtoks = tokens(query)
    if not qtoks:
        return []
    rows = (
        db.query(AiStoredPair)
        .order_by(AiStoredPair.id.desc())
        .limit(500)
        .all()
    )
    scored = []
    seen_q = set()
    for row in rows:
        key = (row.question or "").strip().lower()
        if row.source != "seed" and "Also related" in (row.answer or ""):
            continue
        q_score = jaccard(qtoks, tokens(row.question))
        a_score = jaccard(qtoks, tokens(row.answer))
        score = (0.75 * q_score) + (0.25 * a_score)
        if row.source in ("seed", "seed_v2"):
            score += 0.04 * q_score
        if score < 0.08:
            continue
        if key in seen_q and row.source != "seed":
            continue
        seen_q.add(key)
        scored.append((row, round(min(score, 1.0), 3)))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def _openai_reply(message: str, related: Iterable[tuple], history: list) -> Optional[str]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    related_block = "\n\n".join(
        f"Q: {pair.question}\nA: {pair.answer}" for pair, _ in related
    ) or "None yet."
    hist = "\n".join(history[-8:]) or "New call."
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Maya, a warm, pleasant woman on a live phone call for BUILD FORCES. "
                    "Speak in short, kind sentences like a helpful friend. Never sound male, robotic, or salesy. "
                    "You know the site: Home; Training (all courses, safety/OSHA, equipment, concrete); "
                    "Jobs (find jobs, build resume); Portals (Build Forces crew, Instructors, Homeowners, Companies); "
                    "Resources (how it works, explore, contact); Get Started Free; Log In; languages; "
                    "worker journey of train, certify, find public work. This AI line is 415-555-0148. "
                    "Prefer stored related answers. If unrelated, gently return to the platform. "
                    "If they say hi, hello, or hey, greet them back warmly and ask how you can help. "
                    "Keep replies under 90 words. Do not use markdown or lists."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Related stored answers:\n{related_block}\n\n"
                    f"Recent call:\n{hist}\n\n"
                    f"Current question: {message}"
                ),
            },
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError):
        return None


def compose_local_reply(message: str, related) -> str:
    if is_greeting(message):
        return greeting_reply(message)
    if not related:
        return (
            "I would love to help with that. I can walk you through Home, Training, Jobs, Portals, Resources, or Get Started Free. What would you like to know?"
        )
    seeds = [pair for pair, _score in related if getattr(pair, "source", "") in ("seed", "seed_v2")]
    primary = seeds[0] if seeds else related[0][0]
    extra = None
    for pair, _score in related:
        if pair.id == primary.id:
            continue
        if getattr(pair, "source", "") in ("seed", "seed_v2") and pair.answer != primary.answer:
            extra = pair.answer
            break
    if extra:
        return primary.answer + " " + extra
    return primary.answer


def answer_query(db: Session, message: str, history):
    if is_greeting(message):
        related = find_related(db, "Hi hello hey")
        remote = _openai_reply(message, related, history)
        return remote or greeting_reply(message), related
    lookup = expand_query(message, history)
    related = find_related(db, lookup)
    remote = _openai_reply(lookup, related, history)
    reply = remote or compose_local_reply(message, related)
    return reply, related
