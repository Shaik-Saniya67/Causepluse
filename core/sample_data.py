"""Fictional demo data. Every name, court and case here is invented.

The sample cause list is generated with PyMuPDF so the demo works offline and the
expected results are known: for the demo advocate, 6 matched / 1 needs review / 1 not found.
"""
from __future__ import annotations

from functools import lru_cache

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

DEMO_FILENAME = "DEMO_sample_cause_list.pdf"
DEMO_ADVOCATE = "Adv. Demo Advocate"

# (case_number, year, court, party_names, nickname)
DEMO_CASES = [
    ("CS/412/2023", 2023, "Court 3", "Verma Traders v. Sharma Logistics", "Verma contract suit"),
    ("CRL.M.C. 1180/2025", 2025, "", "Rahul Khanna v. State", "Khanna quashing"),
    ("W.P.(C) 2209/2024", 2024, "", "", "Menon writ"),
    ("BAIL APPLN. 3341/2026", 2026, "", "", "Sethi bail"),
    ("MACP 87/2022", 2022, "", "", "Sunita Devi claim"),
    ("CC 5521/2025", 2025, "", "", "Rao cheque case"),
    ("CS 220/2024", 2024, "", "", "Textile dispute"),      # listed twice -> needs review
    ("ARB.P. 140/2025", 2025, "", "", "Arbitration petition"),  # not in the PDF
]

# (court, judge, [(item, case_as_printed, parties, stage, time)])
_LIST = [
    ("COURT NO. 1", "Hon'ble Ms. Justice A. Example (fictional)", [
        (1, "CS(COMM) 412/2023", "Aster Pharma vs. Boreal Labs", "Arguments", ""),
        (2, "W.P.(C)-2209-2024", "Kavita Menon vs. Union of India|& Ors.", "Hearing", "10:30 AM"),
        (3, "CRL.M.C. 1180/2024", "Imran Qureshi vs. State", "Notice", ""),
        (4, "FAO 55/2025", "Delta Freight vs. Orion Assurance", "Admission", ""),
        (5, "RFA 301/2021", "Joshi Family Trust vs. K. Pillai", "Final Arguments", "12:15 PM"),
    ]),
    ("COURT NO. 2", "Hon'ble Mr. Justice B. Sample (fictional)", [
        (1, "CS 220/2024", "Gupta Brothers vs. Patel & Co.", "Evidence", ""),
        (2, "CC 901/2025", "State vs. Harish Kulkarni", "Charge", ""),
        (3, "MAC.APP. 18/2026", "Oriental Mutual vs. Fatima Bano", "Orders", ""),
        (4, "CRL.REV.P. 77/2025", "Nikhil Arora vs. State", "Arguments", "11:00 AM"),
        (5, "CS 355/2022", "Lotus Estates vs. Ganga Builders", "Reply", ""),
        (6, "EX. 12/2024", "Bharat Steel vs. Mohan Metals", "Execution", ""),
    ]),
    ("COURT NO. 3", "Hon'ble Mr. Justice C. Placeholder (fictional)", [
        (1, "CC 4410/2025", "State vs. Pooja Nambiar", "Evidence", ""),
        (2, "CS 98/2024", "Sunrise Dairy vs. Greenfield Foods", "Arguments", ""),
        (3, "CS(OS) 77/2023", "Anand Rao vs. Kiran Rao", "Mediation", ""),
        (4, "RC.REV. 41/2025", "Suresh Iyer vs. Lalit Mehra", "Notice", "10:00 AM"),
        (5, "CRL.A. 233/2024", "Ravi Teja vs. State", "Hearing", ""),
        (6, "CS No. 412/2023", "Verma Traders vs. Sharma Logistics|Pvt. Ltd.", "Evidence", "11:30 AM"),
        (7, "CC 5521/2025", "State vs. Dinesh Rao", "Evidence", ""),
        (8, "CS 301/2024", "Maple Textiles vs. Indus Dyes", "Arguments", ""),
    ]),
    ("COURT NO. 5", "Hon'ble Ms. Justice D. Illustrative (fictional)", [
        (1, "BAIL APPLN. 3341/2026", "Arjun Sethi vs. State", "Hearing", "10:30 AM"),
        (2, "CRL.M.C. 1180 / 2025", "Rahul Khanna vs. State (NCT)", "Arguments", "11:00 AM"),
        (3, "CRL.M.C. 2210/2025", "Meera Pillai vs. State", "Notice", ""),
        (4, "BAIL APPLN. 3400/2026", "Tarun Bhatt vs. State", "Hearing", ""),
        (5, "CRL.A. 12/2026", "Salim Khan vs. State", "Admission", ""),
        (6, "CRL.REV.P. 190/2025", "Anita Das vs. Ramesh Das", "Orders", ""),
    ]),
    ("COURT NO. 6", "Hon'ble Mr. Justice E. Mockup (fictional)", [
        (1, "ARB.P. 140/2024", "Nova Infra vs. Kestrel Projects", "Appointment", ""),
        (2, "CS 220/2024", "Nair Textiles vs. Bose Exports|Pvt. Ltd.", "Arguments", "02:15 PM"),
        (3, "O.M.P. 88/2025", "Vega Power vs. Titan Grid", "Hearing", ""),
        (4, "CS(COMM) 66/2025", "Cobalt Labs vs. Zephyr Foods", "Evidence", ""),
    ]),
    ("COURT NO. 8", "Hon'ble Ms. Justice F. Specimen (fictional)", [
        (1, "MACP 87/2022", "Sunita Devi vs. Reliance General Ins.", "Final Arguments", "03:00 PM"),
        (2, "MACP 91/2022", "Kamal Singh vs. United Mutual Ins.", "Evidence", ""),
        (3, "MACP 140/2023", "Ritu Sharma vs. Apex Insurance", "Reply", ""),
        (4, "MACP 12/2024", "Joseph Mathew vs. Coastal General", "Orders", ""),
    ]),
]

_X = dict(item=40, case=72, parties=212, stage=420, time=498)


@lru_cache(maxsize=1)
def build_sample_pdf() -> bytes:
    """Built once per process so repeated demo loads hash identically (no duplicate documents)."""
    doc = fitz.open()
    page = doc.new_page()
    y = 50.0

    def new_page():
        nonlocal page, y
        page = doc.new_page()
        y = 50.0

    def put(x, text, size=9, bold=False, yy=None):
        page.insert_text((x, y if yy is None else yy), text, fontsize=size,
                         fontname="hebo" if bold else "helv")

    put(40, "DEMO CAUSE LIST - FICTIONAL DATA FOR CAUSEPULSE", 13, True)
    y += 17
    put(40, "Sample District Court Complex (fictional) - not a real court document", 9)
    y += 15
    put(40, "CAUSE LIST FOR 14 OCTOBER 2026", 10, True)
    y += 26
    for court, judge, rows in _LIST:
        if y > 700:
            new_page()
        put(40, court, 11, True)
        y += 13
        put(40, judge, 8.5)
        y += 17
        for label, x in (("Item", _X["item"]), ("Case No.", _X["case"]), ("Parties", _X["parties"]),
                         ("Stage", _X["stage"]), ("Time", _X["time"])):
            put(x, label, 8.5, True)
        y += 17
        for item, case, parties, stage, time in rows:
            if y > 770:
                new_page()
            first, *wrapped = parties.split("|")
            put(_X["item"], str(item))
            put(_X["case"], case)
            put(_X["parties"], first)
            put(_X["stage"], stage)
            if time:
                put(_X["time"], time)
            for w in wrapped:
                y += 11
                put(_X["parties"], w)
            y += 23
        y += 10
    n = doc.page_count
    for i, p in enumerate(doc):
        p.insert_text((260, 820), f"Page {i + 1} of {n}", fontsize=8, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data
