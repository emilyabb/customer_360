"""Customer 360 source generator for entity-resolution practice.

Builds one deterministic universe of true customers, then renders each of them
into four messy source systems the way a real CRM, billing tool, marketing
platform and help desk would hold them. Every identity record also lands in an
answer key with its true_customer_id, so you can score precision and recall on
your matches.

Batches are daily. Batch 0 is the full history up to --start-date. Batch N holds
only what was created or changed on start_date + N days. Same seed, same files,
so reruns and Airflow backfills are idempotent.

The story baked in: a billing migration on 2025-03-01 re-created customers
instead of mapping them. Of the customers billed before that date, about 1 in 4
Enterprise accounts (1 in 10 everywhere else) now has two billing IDs, and
their revenue is split across both.

Pure Python plus Faker. For local development, manage the environment from the
repository root with uv:

    uv sync
    uv run python generator/c360_generator.py --out ./landing --batch 0
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import string
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from faker import Faker

DEFAULT_START = date(2026, 11, 2)
BILLING_MIGRATION = date(2025, 3, 1)

NICKNAMES = {
    "William": ["Bill", "Will", "Billy"],
    "Robert": ["Bob", "Rob", "Bobby"],
    "Elizabeth": ["Liz", "Beth", "Betsy"],
    "Katherine": ["Kate", "Kathy", "Katie"],
    "Michael": ["Mike", "Mikey"],
    "James": ["Jim", "Jimmy", "Jamie"],
    "Jennifer": ["Jen", "Jenny"],
    "Christopher": ["Chris", "Topher"],
    "Margaret": ["Maggie", "Peggy", "Meg"],
    "Richard": ["Rick", "Rich", "Dick"],
    "Thomas": ["Tom", "Tommy"],
    "Joseph": ["Joe", "Joey"],
    "Patricia": ["Pat", "Patty", "Trish"],
    "Daniel": ["Dan", "Danny"],
    "Jonathan": ["Jon", "Johnny"],
    "Alexander": ["Alex", "Xander"],
    "Rebecca": ["Becky", "Becca"],
    "Samantha": ["Sam", "Sammy"],
    "Anthony": ["Tony"],
    "Victoria": ["Vicky", "Tori"],
    "Nicholas": ["Nick", "Nicky"],
    "Susan": ["Sue", "Susie"],
    "Matthew": ["Matt"],
    "Deborah": ["Deb", "Debbie"],
    "Edward": ["Ed", "Eddie", "Ted"],
}

# Canonical suffix -> the ways people actually type it
LEGAL_SUFFIXES = {
    "Inc": ["Inc", "Inc.", "Incorporated", "INC", ""],
    "LLC": ["LLC", "L.L.C.", "llc", ""],
    "Corp": ["Corp", "Corp.", "Corporation", ""],
    "Co": ["Co", "Co.", "Company", "& Co", ""],
    "Group": ["Group", "Grp", ""],
}

INDUSTRY_WORDS = [
    "Logistics", "Analytics", "Health", "Foods", "Manufacturing", "Capital", "Software",
    "Energy", "Realty", "Labs", "Systems", "Partners", "Supply", "Media", "Dental",
]

TITLES = [
    "Controller", "VP Finance", "Data Analyst", "Operations Manager", "CFO", "IT Director",
    "Procurement Lead", "Office Manager", "Head of Marketing", "CEO", "Accounts Payable Specialist",
]

STREET_ABBREVIATIONS = [
    ("Street", "St"), ("Avenue", "Ave"), ("Road", "Rd"), ("Boulevard", "Blvd"),
    ("Drive", "Dr"), ("Lane", "Ln"), ("Court", "Ct"), ("Suite", "Ste"),
]

PERSONAL_DOMAINS = {"gmail.com": 50, "yahoo.com": 15, "outlook.com": 15, "icloud.com": 10, "hotmail.com": 10}

PHONE_FORMATS = [
    "({a}) {e}-{l}", "{a}-{e}-{l}", "{a}.{e}.{l}", "+1 {a} {e} {l}", "{a}{e}{l}", "1-{a}-{e}-{l}",
]

TIER_WEIGHTS = {"Enterprise": 10, "Mid-Market": 30, "SMB": 60}
CONTACTS_PER_COMPANY_WEIGHT = {"Enterprise": 4, "Mid-Market": 2, "SMB": 1}

# (mu, sigma) for monthly invoice amounts: Enterprise median ~$9.9K, Mid-Market ~$2K, SMB ~$330
INVOICE_LOGNORMAL = {"Enterprise": (9.2, 0.6), "Mid-Market": (7.6, 0.6), "SMB": (5.8, 0.7)}

# Mean days between support tickets
TICKET_GAP_DAYS = {"Enterprise": 45, "Mid-Market": 90, "SMB": 150}

LEAD_SOURCES = {"Organic Search": 35, "Paid Social": 20, "Webinar": 15, "Referral": 12, "Trade Show": 8, "Direct": 10}
PROSPECT_STAGES = {"subscriber": 40, "lead": 45, "marketingqualifiedlead": 15}
CUSTOMER_STAGES = {"lead": 30, "marketingqualifiedlead": 20, "opportunity": 15, "customer": 35}
TOUCH_TYPES = {"email_open": 55, "email_click": 20, "form_fill": 10, "webinar": 8, "demo_request": 7}
CAMPAIGNS = {"Q4 Newsletter": 30, "Year-End Webinar": 15, "Product Launch": 20, "Customer Story": 15, "Pricing Update": 20}
TICKET_SUBJECTS = {
    "Invoice amount looks wrong": 25, "Can't log in": 20, "Export is failing": 15,
    "Request to delete my data": 5, "Update billing address": 15, "Feature request": 20,
}
TICKET_PRIORITIES = {"low": 45, "normal": 38, "high": 13, "urgent": 4}
TICKET_CHANNELS = {"email": 50, "web": 30, "phone": 12, "chat": 8}

# table name -> (system folder, entity folder, columns)
TABLES = {
    "crm_contacts": ("crm", "contacts", [
        "contact_id", "account_id", "first_name", "last_name", "title", "account_name", "email", "phone",
        "mailing_street", "mailing_city", "mailing_state", "mailing_postal_code", "created_date", "last_modified_date",
    ]),
    "billing_customers": ("billing", "customers", [
        "customer_id", "name", "email", "phone", "company_name", "address_line1", "address_line2",
        "city", "state", "postal_code", "currency", "created",
    ]),
    "billing_invoices": ("billing", "invoices", [
        "invoice_id", "customer_id", "invoice_date", "amount_due", "currency", "status",
    ]),
    "marketing_leads": ("marketing", "leads", [
        "lead_id", "firstname", "lastname", "email", "company", "phone", "lifecyclestage", "lead_source",
        "createdate", "lastmodifieddate",
    ]),
    "marketing_touches": ("marketing", "touches", [
        "touch_id", "lead_id", "touch_type", "campaign", "touch_ts",
    ]),
    "support_requesters": ("support", "requesters", [
        "requester_id", "name", "email", "phone", "organization", "created_at",
    ]),
    "support_tickets": ("support", "tickets", [
        "ticket_id", "requester_id", "subject", "priority", "channel", "status", "created_at", "solved_at",
    ]),
    "answer_key": ("_answer_key", "answer_key", [
        "source_system", "source_table", "source_record_id", "true_customer_id",
    ]),
}


@dataclass(frozen=True)
class Company:
    idx: int
    base: str
    suffix: str
    domain: str
    tier: str
    street: str
    city: str
    state: str
    zip5: str


@dataclass(frozen=True)
class Customer:
    idx: int
    true_id: str
    first: str
    last: str
    title: str
    company: Company
    work_email: str
    personal_email: str
    phone: str
    is_prospect: bool
    joined: datetime


# ---------------------------------------------------------------------------
# Deterministic randomness: every record gets its own RNG keyed by what it is,
# so output never depends on loop order or on which batch you run.
# ---------------------------------------------------------------------------

def _stable_int(*parts) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _rng(*parts) -> random.Random:
    return random.Random(_stable_int(*parts))


_ALNUM = string.ascii_letters + string.digits


def _stable_code(length: int, *parts) -> str:
    rng = _rng("code", *parts)
    return "".join(rng.choice(_ALNUM) for _ in range(length))


def _pick(rng: random.Random, weights: dict[str, int]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _at(day: date, rng: random.Random) -> datetime:
    return datetime.combine(day, time(rng.randint(7, 19), rng.randint(0, 59), rng.randint(0, 59)), tzinfo=timezone.utc)


def _add_months(day: date, months: int) -> date:
    years, month_idx = divmod(day.month - 1 + months, 12)
    return date(day.year + years, month_idx + 1, min(day.day, 28))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


# ---------------------------------------------------------------------------
# Mess: the ways humans and integrations mangle the same fact
# ---------------------------------------------------------------------------

def _typo(text: str, rng: random.Random) -> str:
    if len(text) < 4:
        return text
    i = rng.randrange(1, len(text) - 1)
    kind = rng.random()
    if kind < 0.4:
        return text[:i] + text[i + 1] + text[i] + text[i + 2:]  # swap two letters
    if kind < 0.7:
        return text[:i] + text[i + 1:]  # drop a letter
    return text[:i] + text[i] + text[i:]  # double a letter


def _case_drift(text: str, rng: random.Random) -> str:
    return text.upper() if rng.random() < 0.5 else text.lower()


def _render_first(c: Customer, rng: random.Random, mess: float) -> str:
    name = c.first
    if name in NICKNAMES and rng.random() < mess:
        name = rng.choice(NICKNAMES[name])
    if rng.random() < mess * 0.08:
        name = _typo(name, rng)
    if rng.random() < mess * 0.10:
        name = _case_drift(name, rng)
    return name


def _render_last(c: Customer, rng: random.Random, mess: float) -> str:
    name = c.last
    if rng.random() < mess * 0.05:
        name = _typo(name, rng)
    if rng.random() < mess * 0.08:
        name = _case_drift(name, rng)
    return name


def _render_full_name(first: str, last: str, rng: random.Random, mess: float) -> str:
    r = rng.random()
    if r < mess * 0.25:
        return f"{last}, {first}"
    if r < mess * 0.40:
        return f"{first[0]}. {last}"
    if r < mess * 0.55:
        return f"{first} {last}".lower()
    return f"{first} {last}"


def _render_company(co: Company, rng: random.Random, mess: float) -> str:
    name = co.base
    if "&" in name and rng.random() < mess * 0.4:
        name = name.replace("&", "and")
    suffix = rng.choice(LEGAL_SUFFIXES[co.suffix]) if rng.random() < mess else co.suffix
    full = f"{name} {suffix}".strip()
    if rng.random() < mess * 0.15:
        full = _typo(full, rng)
    if rng.random() < mess * 0.20:
        full = _case_drift(full, rng)
    if rng.random() < 0.03:
        full = "The " + full
    return full


def _render_email(email: str, rng: random.Random, mess: float) -> str:
    local, domain = email.split("@")
    if domain == "gmail.com" and rng.random() < mess * 0.4:
        if rng.random() < 0.5 and len(local) > 3:
            i = rng.randrange(1, len(local) - 1)
            local = local[:i] + "." + local[i:]  # Gmail ignores dots
        else:
            local = f"{local}+{rng.choice(['promo', 'news', 'work', 'shop'])}"  # and plus tags
    if rng.random() < mess * 0.02 and domain.endswith(".com"):
        domain = domain[:-4] + ".con"
    out = f"{local}@{domain}"
    r = rng.random()
    if r < mess * 0.05:
        out = out.upper()
    elif r < mess * 0.12:
        out = local.capitalize() + "@" + domain
    return out


def _render_phone(digits: str, rng: random.Random, mess: float) -> str:
    fmt = rng.choice(PHONE_FORMATS) if rng.random() < mess else PHONE_FORMATS[0]
    out = fmt.format(a=digits[:3], e=digits[3:6], l=digits[6:])
    if rng.random() < 0.05:
        out += f" x{rng.randint(10, 999)}"
    return out


def _render_street(street: str, rng: random.Random, mess: float) -> str:
    out = street
    for long, short in STREET_ABBREVIATIONS:
        if long in out and rng.random() < mess:
            out = out.replace(long, short)
    if rng.random() < mess * 0.10:
        out = _case_drift(out, rng)
    return out


def _render_zip(zip5: str, rng: random.Random, mess: float) -> str:
    return f"{zip5}-{rng.randint(1000, 9999)}" if rng.random() < mess * 0.3 else zip5


# ---------------------------------------------------------------------------
# The universe of true customers
# ---------------------------------------------------------------------------

def _make_company(fake: Faker, seed: int, i: int) -> Company:
    rng = _rng(seed, "company", i)
    fake.seed_instance(_stable_int(seed, "company-faker", i))
    if rng.random() < 0.7:
        base = f"{fake.last_name()} {rng.choice(INDUSTRY_WORDS)}"
    else:
        base = f"{fake.last_name()} & {fake.last_name()}"
    street = fake.street_address()
    if rng.random() < 0.3:
        street += f" Suite {rng.randint(100, 950)}"
    state = fake.state_abbr(include_territories=False, include_freely_associated_states=False)
    return Company(
        idx=i,
        base=base,
        suffix=rng.choice(list(LEGAL_SUFFIXES)),
        domain=_slug(base) + rng.choice([".com", ".com", ".com", ".io", ".net"]),
        tier=_pick(rng, TIER_WEIGHTS),
        street=street,
        city=fake.city(),
        state=state,
        zip5=fake.zipcode_in_state(state),
    )


def _make_customer(fake: Faker, seed: int, i: int, companies: list[Company], cum_weights: list[int], start: date) -> Customer:
    rng = _rng(seed, "customer", i)
    fake.seed_instance(_stable_int(seed, "customer-faker", i))
    company = rng.choices(companies, cum_weights=cum_weights)[0]
    # Over-sample names that have nicknames so the matcher has to deal with them
    first = rng.choice(list(NICKNAMES)) if rng.random() < 0.35 else fake.first_name()
    last = fake.last_name()
    f, l = _slug(first), _slug(last)
    work_local = f"{f}.{l}" if rng.random() < 0.7 else f"{f[0]}{l}"
    personal_local = rng.choice([f"{f}{l}", f"{f}.{l}", f"{f[0]}{l}{rng.randint(1, 99)}", f"{l}{f}{rng.randint(70, 99)}"])
    # 90% joined before the start date; 10% trickle in over the 60 days after it
    if rng.random() < 0.9:
        joined_day = start - timedelta(days=rng.randint(30, 1095))
    else:
        joined_day = start + timedelta(days=rng.randint(1, 60))
    return Customer(
        idx=i,
        true_id=f"TC-{i:06d}",
        first=first,
        last=last,
        title=rng.choice(TITLES),
        company=company,
        work_email=f"{work_local}@{company.domain}",
        personal_email=f"{personal_local}@{_pick(rng, PERSONAL_DOMAINS)}",
        phone=f"{rng.randint(201, 989)}{rng.randint(201, 999)}{rng.randint(0, 9999):04d}",
        is_prospect=rng.random() < 0.15,
        joined=_at(joined_day, rng),
    )


def build_universe(n_customers: int, seed: int, start: date) -> list[Customer]:
    fake = Faker("en_US")
    companies = [_make_company(fake, seed, i) for i in range(max(1, n_customers * 5 // 8))]
    cum_weights, total = [], 0
    for co in companies:
        total += CONTACTS_PER_COMPANY_WEIGHT[co.tier]
        cum_weights.append(total)
    return [_make_customer(fake, seed, i, companies, cum_weights, start) for i in range(n_customers)]


def _membership(seed: int, c: Customer) -> dict[str, int]:
    """How many records this customer has in each system (0 = absent)."""
    rng = _rng(seed, "membership", c.idx)
    if c.is_prospect:
        return {"crm": 0, "billing": 0, "marketing": rng.choices([1, 2, 3], [60, 30, 10])[0], "support": 0}
    migration_dup_rate = 0.25 if c.company.tier == "Enterprise" else 0.10
    in_crm, crm_dup = rng.random() < 0.95, rng.random() < 0.08
    in_billing, billing_dup = rng.random() < 0.75, rng.random() < migration_dup_rate
    in_marketing, n_leads = rng.random() < 0.70, rng.choices([1, 2, 3], [55, 30, 15])[0]
    in_support, support_dup = rng.random() < 0.50, rng.random() < 0.25
    m = {
        "crm": (2 if crm_dup else 1) if in_crm else 0,
        # Only customers who existed before the migration got re-created
        "billing": (2 if billing_dup and c.joined.date() < BILLING_MIGRATION else 1) if in_billing else 0,
        "marketing": n_leads if in_marketing else 0,
        "support": (2 if support_dup else 1) if in_support else 0,
    }
    if not any(m.values()):
        m["crm"] = 1
    return m


# ---------------------------------------------------------------------------
# Source-system records
# ---------------------------------------------------------------------------

def _sfdc_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _iso_z(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _crm_contact(seed: int, c: Customer, d: int) -> tuple[dict, datetime]:
    rng = _rng(seed, "crm", c.idx, d)
    co, mess = c.company, 0.3
    if d == 0:
        created = c.joined + timedelta(days=rng.randint(0, 14), minutes=rng.randint(0, 600))
        account_id = "001" + _stable_code(15, seed, "account", co.idx)
    else:
        # A second rep keys the same person in, half the time under a duplicate account
        created = c.joined + timedelta(days=rng.randint(20, 500), minutes=rng.randint(0, 600))
        dup_account = rng.random() < 0.5
        account_id = "001" + (_stable_code(15, seed, "account", co.idx, "dup", c.idx) if dup_account
                              else _stable_code(15, seed, "account", co.idx))
    email = c.work_email if rng.random() < 0.92 else c.personal_email
    record = {
        "contact_id": "003" + _stable_code(15, seed, "crm", c.idx, d),
        "account_id": account_id,
        "first_name": _render_first(c, rng, mess),
        "last_name": _render_last(c, rng, mess),
        "title": c.title,
        "account_name": _render_company(co, rng, mess),
        "email": _render_email(email, rng, mess) if rng.random() > 0.03 else "",
        "phone": _render_phone(c.phone, rng, mess) if rng.random() < 0.85 else "",
        "mailing_street": _render_street(co.street, rng, mess),
        "mailing_city": co.city,
        "mailing_state": co.state,
        "mailing_postal_code": _render_zip(co.zip5, rng, mess),
        "created_date": _sfdc_ts(created),
        "last_modified_date": _sfdc_ts(created),
    }
    return record, created


def _crm_update(seed: int, c: Customer, d: int, record: dict, day: date, batch: int) -> dict | None:
    """~3% of existing contacts get edited on any given day (new phone or an office move)."""
    rng = _rng(seed, "crm-update", c.idx, d, batch)
    if rng.random() >= 0.03:
        return None
    fake = Faker("en_US")
    fake.seed_instance(_stable_int(seed, "crm-update-faker", c.idx, d, batch))
    updated = dict(record)
    if rng.random() < 0.5:
        new_phone = f"{rng.randint(201, 989)}{rng.randint(201, 999)}{rng.randint(0, 9999):04d}"
        updated["phone"] = _render_phone(new_phone, rng, 0.3)
    else:
        updated["mailing_street"] = fake.street_address()
    updated["last_modified_date"] = _sfdc_ts(_at(day, rng))
    return updated


def _billing_customer(fake: Faker, seed: int, c: Customer, d: int) -> tuple[dict, datetime]:
    rng = _rng(seed, "billing", c.idx, d)
    fake.seed_instance(_stable_int(seed, "billing-faker", c.idx, d))
    co, mess = c.company, 0.5
    if d == 0:
        created = c.joined + timedelta(days=rng.randint(0, 3), minutes=rng.randint(0, 600))
    else:
        created = _at(BILLING_MIGRATION + timedelta(days=rng.randint(0, 20)), rng)
    first, last = _render_first(c, rng, mess), _render_last(c, rng, mess)
    if rng.random() < 0.15:
        email = f"{rng.choice(['ap', 'billing', 'accounts', 'finance'])}@{co.domain}"  # shared AP inbox
    else:
        email = _render_email(c.work_email, rng, mess)
    if rng.random() < 0.6:
        line1, line2 = _render_street(co.street, rng, mess), ""
        city, state, postal = co.city, co.state, _render_zip(co.zip5, rng, mess)
    else:
        # Separate remit-to address
        line1 = f"PO Box {rng.randint(100, 99999)}" if rng.random() < 0.5 else fake.street_address()
        line2 = "Attn: Accounts Payable" if rng.random() < 0.4 else ""
        city, state, postal = co.city, co.state, co.zip5
    record = {
        "customer_id": "cus_" + _stable_code(14, seed, "billing", c.idx, d),
        "name": f"{first} {last}" if rng.random() < 0.6 else _render_company(co, rng, mess),
        "email": email,
        "phone": _render_phone(c.phone, rng, mess) if rng.random() < 0.6 else "",
        "company_name": _render_company(co, rng, mess),
        "address_line1": line1,
        "address_line2": line2,
        "city": city,
        "state": state,
        "postal_code": postal,
        "currency": "usd",
        "created": str(int(created.timestamp())),  # Stripe sends epoch seconds
    }
    return record, created


def _invoices(seed: int, c: Customer, d: int, customer_id: str, created: datetime, stop_on: date | None, hi: date):
    """Monthly invoices from account creation until hi (or the migration, for a migrated account)."""
    mu, sigma = INVOICE_LOGNORMAL[c.company.tier]
    k, first_day = 0, created.date()
    while True:
        inv_day = _add_months(first_day, k)
        if inv_day > hi or (stop_on and inv_day >= stop_on):
            return
        rng = _rng(seed, "invoice", c.idx, d, k)
        amount, r = rng.lognormvariate(mu, sigma), rng.random()
        if (hi - inv_day).days <= 30:
            status = "open" if r < 0.6 else "paid"
        else:
            status = "paid" if r < 0.95 else ("void" if r < 0.98 else "uncollectible")
        yield inv_day, {
            "invoice_id": "in_" + _stable_code(14, seed, "invoice", c.idx, d, k),
            "customer_id": customer_id,
            "invoice_date": inv_day.isoformat(),
            "amount_due": f"{amount:.2f}",
            "currency": "usd",
            "status": status,
        }
        k += 1


def _lead(seed: int, c: Customer, li: int, created: datetime) -> dict:
    rng = _rng(seed, "lead", c.idx, li)
    mess = 0.8
    email = c.personal_email if rng.random() < (0.5 if c.is_prospect else 0.45) else c.work_email
    stage = _pick(rng, PROSPECT_STAGES if c.is_prospect else CUSTOMER_STAGES)
    return {
        "lead_id": str(_stable_int(seed, "lead-id", c.idx, li) % 10**9),
        "firstname": _render_first(c, rng, mess),
        "lastname": _render_last(c, rng, mess),
        "email": _render_email(email, rng, mess),
        "company": "" if rng.random() < 0.25 else _render_company(c.company, rng, mess),
        "phone": "" if rng.random() < 0.5 else _render_phone(c.phone, rng, mess),
        "lifecyclestage": stage,
        "lead_source": _pick(rng, LEAD_SOURCES),
        "createdate": _iso_z(created),
        "lastmodifieddate": _iso_z(created + timedelta(days=rng.randint(0, 30))),
    }


def _touches(seed: int, c: Customer, li: int, lead_id: str, created: datetime, hi: date):
    rng = _rng(seed, "touches", c.idx, li)
    cap = min(25, int(rng.paretovariate(1.1)))  # most leads touch once or twice, a few engage a lot
    ts = created
    for j in range(cap):
        ts += timedelta(days=rng.expovariate(1 / 21))
        if ts.date() > hi:
            return
        yield ts, {
            "touch_id": str(_stable_int(seed, "touch", c.idx, li, j) % 10**10),
            "lead_id": lead_id,
            "touch_type": _pick(rng, TOUCH_TYPES),
            "campaign": _pick(rng, CAMPAIGNS),
            "touch_ts": _iso_z(ts),
        }


def _requester(seed: int, c: Customer, s: int, created: datetime) -> dict:
    rng = _rng(seed, "requester", c.idx, s)
    mess = 0.8
    work_first = _rng(seed, "requester-email", c.idx).random() < 0.7
    # The second requester record is the same person writing in from the other inbox
    use_work = work_first if s == 0 else not work_first
    first, last = _render_first(c, rng, mess), _render_last(c, rng, mess)
    return {
        "requester_id": str(_stable_int(seed, "requester-id", c.idx, s) % 10**10),
        "name": _render_full_name(first, last, rng, mess),
        "email": _render_email(c.work_email if use_work else c.personal_email, rng, mess),
        "phone": "" if rng.random() < 0.4 else _render_phone(c.phone, rng, mess),
        "organization": "" if rng.random() < 0.4 else _render_company(c.company, rng, mess),
        "created_at": _iso_z(created),
    }


def _tickets(seed: int, c: Customer, s: int, requester_id: str, created: datetime, hi: date):
    """The first ticket opens the requester; Enterprise customers write in more often."""
    rng = _rng(seed, "tickets", c.idx, s)
    cap = min(30, int(rng.paretovariate(0.9)))
    gap = TICKET_GAP_DAYS[c.company.tier]
    ts = created
    for j in range(cap):
        if j:
            ts += timedelta(days=rng.expovariate(1 / gap))
        if ts.date() > hi:
            return
        priority = _pick(rng, TICKET_PRIORITIES)
        solved = ts + timedelta(hours=rng.expovariate(1 / {"urgent": 4, "high": 12, "normal": 30, "low": 60}[priority]))
        is_solved = solved.date() <= hi
        yield ts, {
            "ticket_id": str(_stable_int(seed, "ticket", c.idx, s, j) % 10**10),
            "requester_id": requester_id,
            "subject": _pick(rng, TICKET_SUBJECTS),
            "priority": priority,
            "channel": _pick(rng, TICKET_CHANNELS),
            "status": "solved" if is_solved else rng.choice(["new", "open", "pending"]),
            "created_at": _iso_z(ts),
            "solved_at": _iso_z(solved) if is_solved else "",
        }


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------

def generate_batch(batch: int = 0, start: date = DEFAULT_START, n_customers: int = 7000, seed: int = 42) -> dict[str, list[dict]]:
    """Every record created (or changed) inside this batch's window, keyed by table name."""
    hi = start + timedelta(days=batch)
    lo = None if batch == 0 else hi - timedelta(days=1)

    def in_window(ts: datetime | date) -> bool:
        day = ts.date() if isinstance(ts, datetime) else ts
        return (lo is None or day > lo) and day <= hi

    fake = Faker("en_US")
    out: dict[str, list[dict]] = {name: [] for name in TABLES}

    def key(system: str, table: str, record_id: str, c: Customer) -> None:
        out["answer_key"].append({
            "source_system": system, "source_table": table, "source_record_id": record_id, "true_customer_id": c.true_id,
        })

    for c in build_universe(n_customers, seed, start):
        m = _membership(seed, c)

        for d in range(m["crm"]):
            record, created = _crm_contact(seed, c, d)
            if in_window(created):
                out["crm_contacts"].append(record)
                key("crm", "contacts", record["contact_id"], c)
            elif batch and created.date() < hi:
                updated = _crm_update(seed, c, d, record, hi, batch)
                if updated:
                    out["crm_contacts"].append(updated)

        for d in range(m["billing"]):
            record, created = _billing_customer(fake, seed, c, d)
            if in_window(created):
                out["billing_customers"].append(record)
                key("billing", "customers", record["customer_id"], c)
            stop_on = BILLING_MIGRATION if d == 0 and m["billing"] == 2 else None
            for inv_day, invoice in _invoices(seed, c, d, record["customer_id"], created, stop_on, hi):
                if in_window(inv_day):
                    out["billing_invoices"].append(invoice)

        lead_created = c.joined - timedelta(days=_rng(seed, "lead-start", c.idx).randint(30, 240))
        for li in range(m["marketing"]):
            if li:
                lead_created += timedelta(days=_rng(seed, "lead-gap", c.idx, li).randint(30, 400))
            if lead_created.date() > hi:
                break
            record = _lead(seed, c, li, lead_created)
            if in_window(lead_created):
                out["marketing_leads"].append(record)
                key("marketing", "leads", record["lead_id"], c)
            for ts, touch in _touches(seed, c, li, record["lead_id"], lead_created, hi):
                if in_window(ts):
                    out["marketing_touches"].append(touch)

        req_created = c.joined + timedelta(days=_rng(seed, "support-start", c.idx).randint(10, 600))
        for s in range(m["support"]):
            if s:
                req_created += timedelta(days=_rng(seed, "support-gap", c.idx).randint(1, 300))
            if req_created.date() > hi:
                break
            record = _requester(seed, c, s, req_created)
            if in_window(req_created):
                out["support_requesters"].append(record)
                key("support", "requesters", record["requester_id"], c)
            for ts, ticket in _tickets(seed, c, s, record["requester_id"], req_created, hi):
                if in_window(ts):
                    out["support_tickets"].append(ticket)

    return out


def write_batch(out_root: str | Path, batch: int = 0, start: date = DEFAULT_START,
                n_customers: int = 7000, seed: int = 42) -> list[dict]:
    """Write one batch as CSVs: <out_root>/<system>/<entity>/batch_date=YYYY-MM-DD/<entity>_bNNNN.csv.

    The answer key goes under _answer_key/, which Spark and Auto Loader skip by default,
    so it never leaks into your bronze tables.
    """
    batch_date = (start + timedelta(days=batch)).isoformat()
    tables = generate_batch(batch, start, n_customers, seed)
    written = []
    for name, (system, entity, columns) in TABLES.items():
        folder = Path(out_root) / system / entity / f"batch_date={batch_date}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{entity}_b{batch:04d}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            writer.writerows(tables[name])
        written.append({"table": name, "rows": len(tables[name]), "path": str(path)})
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one daily batch of Customer 360 source files.")
    parser.add_argument("--out", default="landing", help="Root folder for the landing files")
    parser.add_argument("--batch", type=int, default=0, help="0 = full history; N = start date + N days")
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--n-customers", type=int, default=7000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    for row in write_batch(args.out, args.batch, args.start_date, args.n_customers, args.seed):
        print(f"{row['table']:<20} {row['rows']:>8,}  {row['path']}")


if __name__ == "__main__":
    main()
