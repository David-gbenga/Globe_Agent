"""Build data/expenses.db. Deterministic — same seed, same database.

    python scripts/build_db.py
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "expenses.db"

SEED = 20260115
rng = random.Random(SEED)

SCHEMA = """
DROP TABLE IF EXISTS expense_lines;
DROP TABLE IF EXISTS expense_reports;
DROP TABLE IF EXISTS employees;

CREATE TABLE employees (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    department  TEXT NOT NULL,
    cost_centre TEXT,
    manager_id  TEXT REFERENCES employees(id),
    status      TEXT NOT NULL DEFAULT 'active'   -- active | departed
);

CREATE TABLE expense_reports (
    id           TEXT PRIMARY KEY,
    employee_id  TEXT NOT NULL REFERENCES employees(id),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL,  -- draft|submitted|approved|rejected|paid
    submitted_at TEXT,
    total_gbp    REAL NOT NULL DEFAULT 0,
    cost_centre  TEXT
);

CREATE TABLE expense_lines (
    id             TEXT PRIMARY KEY,
    report_id      TEXT NOT NULL REFERENCES expense_reports(id),
    category       TEXT NOT NULL,
    description    TEXT NOT NULL,
    amount_gbp     REAL NOT NULL,
    incurred_on    TEXT NOT NULL,
    receipt_missing INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_reports_employee ON expense_reports(employee_id);
CREATE INDEX idx_lines_report ON expense_lines(report_id);
"""

FIRST = ["Amara", "Ben", "Chidi", "Dara", "Elena", "Farid", "Grace", "Hugo", "Ines",
         "Jonas", "Kiran", "Lena", "Mateo", "Nadia", "Omar", "Priya", "Quinn", "Rosa",
         "Sami", "Tomas", "Ursula", "Viktor", "Wen", "Xenia", "Yuki", "Zane", "Anya",
         "Bruno", "Clara", "Diego", "Esme", "Felix", "Gia", "Hana", "Ivo", "Juno",
         "Kai", "Liv", "Mira", "Noor"]
LAST = ["Okafor", "Wright", "Nwosu", "Singh", "Marchetti", "Haddad", "Bennett", "Lang",
        "Ferreira", "Berg", "Rao", "Novak", "Alvarez", "Rahman", "Aziz", "Menon",
        "Doyle", "Silva", "Yilmaz", "Novotny", "Klein", "Petrov", "Zhang", "Kovac",
        "Tanaka", "Whitfield", "Ivanova", "Costa", "Fischer", "Moreno", "Duval",
        "Adler", "Rossi", "Sato", "Horvat", "Larsen", "Chen", "Nilsen", "Kapoor", "Said"]

DEPARTMENTS = {
    "Engineering": "CC-1010",
    "Data & AI": "CC-1020",
    "Sales": "CC-2010",
    "Marketing": "CC-2020",
    "Finance": "CC-3010",
    "People": "CC-3020",
}

CATEGORIES = [
    ("travel", ["Flight LHR-JFK", "Flight LHR-FRA", "Rail London-Manchester",
                "Flight LHR-SIN", "Rail Eurostar London-Paris"]),
    ("accommodation", ["Hotel, 3 nights", "Hotel, 1 night", "Serviced apartment, 14 nights",
                       "Hotel, 2 nights"]),
    ("meals", ["Dinner", "Lunch", "Breakfast", "Evening meal, conference"]),
    ("ground_transport", ["Airport taxi", "Ride-hail to client site", "Tube travel",
                          "Car rental, 2 days", "Airport parking"]),
    ("client_entertainment", ["Client dinner, 4 attendees", "Client lunch, 2 attendees"]),
    ("equipment", ["Monitor", "Headset", "Docking station", "Laptop stand"]),
    ("software", ["Design tool annual licence", "Analytics seat"]),
    ("training", ["Conference ticket", "Certification exam fee"]),
]

TRIPS = ["Client visit, New York", "Team offsite, Lisbon", "Conference, Berlin",
         "Vendor workshop, Dublin", "Customer QBR, Singapore", "Recruiting, Manchester",
         "Sales kickoff, Madrid", "Partner summit, Amsterdam", "Home office setup",
         "October expenses", "November expenses", "Q1 travel", "Site visit, Warsaw"]


def build() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    # ---- employees: 40, in a real three-level hierarchy -------------------
    employees: list[tuple] = []
    used = set()

    def make_name(i: int) -> tuple[str, str]:
        while True:
            name = f"{FIRST[i % len(FIRST)]} {LAST[(i * 7 + 3) % len(LAST)]}"
            if name not in used:
                used.add(name)
                return name, name.lower().replace(" ", ".") + "@example.com"
            i += 1

    # E001 is the CFO, no manager.
    name, email = make_name(0)
    employees.append(("E001", name, email, "Finance", "CC-3010", None, "active"))

    # six department heads report to the CFO
    heads = {}
    for idx, (dept, cc) in enumerate(DEPARTMENTS.items(), start=2):
        eid = f"E{idx:03d}"
        name, email = make_name(idx)
        employees.append((eid, name, email, dept, cc, "E001", "active"))
        heads[dept] = eid

    # remaining employees report to a department head, some to a mid-level lead
    leads: dict[str, list[str]] = {d: [] for d in DEPARTMENTS}
    next_id = len(employees) + 1
    dept_cycle = list(DEPARTMENTS.items())
    while len(employees) < 40:
        dept, cc = dept_cycle[next_id % len(dept_cycle)]
        eid = f"E{next_id:03d}"
        name, email = make_name(next_id)
        # first two per department become leads under the head; others report to a lead
        if len(leads[dept]) < 2:
            manager = heads[dept]
            leads[dept].append(eid)
        else:
            manager = rng.choice(leads[dept])
        status = "active"
        cost_centre = cc
        employees.append((eid, name, email, dept, cost_centre, manager, status))
        next_id += 1

    # edge case: one departed employee
    employees[33] = employees[33][:6] + ("departed",)
    departed_id = employees[33][0]

    conn.executemany(
        "INSERT INTO employees (id,name,email,department,cost_centre,manager_id,status) "
        "VALUES (?,?,?,?,?,?,?)",
        employees,
    )

    # ---- reports and lines ------------------------------------------------
    statuses = ["draft", "submitted", "approved", "paid", "rejected"]
    weights = [12, 25, 25, 30, 8]
    start = date(2025, 9, 1)

    reports: list[tuple] = []
    lines: list[tuple] = []
    rid = 1
    lid = 1

    for emp in employees:
        eid, _, _, dept, cc, _, status = emp
        n_reports = rng.randint(3, 7)
        for _ in range(n_reports):
            report_id = f"R{rid:04d}"
            rid += 1
            submitted = start + timedelta(days=rng.randint(0, 300))
            rstatus = rng.choices(statuses, weights)[0]
            n_lines = rng.randint(2, 6)
            total = 0.0
            for _ in range(n_lines):
                cat, descs = rng.choice(CATEGORIES)
                base = {
                    "travel": (90, 1400),
                    "accommodation": (110, 900),
                    "meals": (8, 70),
                    "ground_transport": (6, 180),
                    "client_entertainment": (60, 800),
                    "equipment": (25, 450),
                    "software": (90, 900),
                    "training": (150, 1900),
                }[cat]
                amount = round(rng.uniform(*base), 2)
                total += amount
                lines.append((
                    f"L{lid:05d}", report_id, cat, rng.choice(descs), amount,
                    (submitted - timedelta(days=rng.randint(1, 40))).isoformat(),
                    1 if rng.random() < 0.06 else 0,
                ))
                lid += 1
            reports.append((
                report_id, eid, rng.choice(TRIPS), rstatus,
                submitted.isoformat() if rstatus != "draft" else None,
                round(total, 2), cc,
            ))

    # ---- planted edge cases ----------------------------------------------
    # 1. a report belonging to the departed employee, still unpaid
    reports.append((f"R{rid:04d}", departed_id, "Final claim, September",
                    "submitted", "2026-02-02", 412.55, "CC-2010"))
    for cat, desc, amt in [("travel", "Rail London-Manchester", 128.40),
                           ("meals", "Dinner", 34.15),
                           ("accommodation", "Hotel, 1 night", 250.00)]:
        lines.append((f"L{lid:05d}", f"R{rid:04d}", cat, desc, amt, "2026-01-20", 0))
        lid += 1
    rid += 1

    # 2. a duplicate submission — same employee, same trip, same total, two ids
    dup_owner = "E012"
    for _ in range(2):
        reports.append((f"R{rid:04d}", dup_owner, "Conference, Berlin", "submitted",
                        "2026-01-28", 1284.90, "CC-1020"))
        for cat, desc, amt in [("travel", "Flight LHR-FRA", 342.10),
                               ("accommodation", "Hotel, 3 nights", 690.00),
                               ("training", "Conference ticket", 252.80)]:
            lines.append((f"L{lid:05d}", f"R{rid:04d}", cat, desc, amt, "2026-01-14", 0))
            lid += 1
        rid += 1

    # 3. a report with a null cost centre and a missing receipt over the limit
    reports.append((f"R{rid:04d}", "E020", "Customer QBR, Singapore", "submitted",
                    "2026-02-10", 3890.25, None))
    for cat, desc, amt, miss in [("travel", "Flight LHR-SIN", 2740.00, 0),
                                 ("accommodation", "Hotel, 2 nights", 610.25, 0),
                                 ("client_entertainment", "Client dinner, 4 attendees", 540.00, 1)]:
        lines.append((f"L{lid:05d}", f"R{rid:04d}", cat, desc, amt, "2026-02-01", miss))
        lid += 1
    rid += 1

    # 4. a high-value report owned by the CFO, for authorization tests
    reports.append((f"R{rid:04d}", "E001", "Board offsite, Zurich", "approved",
                    "2026-01-30", 11450.00, "CC-3010"))
    for cat, desc, amt in [("travel", "Flight LHR-ZRH", 890.00),
                           ("accommodation", "Hotel, 3 nights", 2460.00),
                           ("client_entertainment", "Board dinner", 8100.00)]:
        lines.append((f"L{lid:05d}", f"R{rid:04d}", cat, desc, amt, "2026-01-22", 0))
        lid += 1

    conn.executemany(
        "INSERT INTO expense_reports (id,employee_id,title,status,submitted_at,total_gbp,cost_centre) "
        "VALUES (?,?,?,?,?,?,?)",
        reports,
    )
    conn.executemany(
        "INSERT INTO expense_lines (id,report_id,category,description,amount_gbp,incurred_on,receipt_missing) "
        "VALUES (?,?,?,?,?,?,?)",
        lines,
    )
    conn.commit()

    print(f"employees      {len(employees)}")
    print(f"expense_reports {len(reports)}")
    print(f"expense_lines   {len(lines)}")
    print(f"written to      {DB}")
    conn.close()


if __name__ == "__main__":
    build()
