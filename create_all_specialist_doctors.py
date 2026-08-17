#!/usr/bin/env python3
"""
create_all_specialist_doctors.py — MediConnect demo-data generator

Creates one doctor account for EVERY specialty the AI recommendation
engine (ai/ai_api.py) can output, so that whatever specialty the AI
"Get Recommendation" demo suggests, a matching doctor actually exists
in the app for your faculty demo. Also works through the real
backend/register.php API (passwords get hashed normally) and saves
every generated account to a CSV file.

Specialties covered (taken directly from ai/ai_api.py's SPECIALTY_RULES
and get_specialty_from_disease mappings):
    Neurologist, Cardiologist, Dermatologist, Dentist, Psychiatrist,
    ENT Specialist, Gastroenterologist, Pulmonologist,
    Orthopedic Specialist, Ophthalmologist, General Physician
Plus one extra commonly-expected specialty not in the AI's list:
    Pediatrician

USAGE
-----
    python3 create_all_specialist_doctors.py
    python3 create_all_specialist_doctors.py --base-url http://localhost/mediconnect
    python3 create_all_specialist_doctors.py --per-specialty 2
    python3 create_all_specialist_doctors.py --output demo_doctors.csv

No extra packages needed — uses only the Python standard library.
"""

import argparse
import csv
import json
import random
import string
import urllib.request
import urllib.error

# --------------------------------------------------------------------------
# Specialties — exact strings the AI (ai_api.py) actually returns,
# so patient bookings after an AI recommendation match a real doctor.
# --------------------------------------------------------------------------

SPECIALTIES = [
    "Neurologist",
    "Cardiologist",
    "Dermatologist",
    "Dentist",
    "Psychiatrist",
    "ENT Specialist",
    "Gastroenterologist",
    "Pulmonologist",
    "Orthopedic Specialist",
    "Ophthalmologist",
    "General Physician",
    "Pediatrician",     # not produced by the AI directly, but expected by faculty for a full demo
]

FIRST_NAMES = [
    "Rafiq", "Nusrat", "Kamal", "Farzana", "Shakil", "Mitu", "Tanvir",
    "Sadia", "Imran", "Nabila", "Rakib", "Sumaiya", "Hasan", "Priya",
    "Arif", "Lamia", "Junaid", "Tania", "Rezaul", "Mahin",
]

LAST_NAMES = [
    "Ahmed", "Islam", "Hossain", "Rahman", "Chowdhury", "Karim", "Akter",
    "Hasan", "Uddin", "Khan", "Sultana", "Alam",
]

DEFAULT_BASE_URL = "http://localhost/mediconnect"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def random_password(length=10):
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def make_name(used_names):
    while True:
        name = f"Dr. {random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in used_names:
            used_names.add(name)
            return name


def make_email(name, used_emails):
    base = name.lower().replace("dr. ", "").replace(" ", ".")
    for suffix in ["", "1", "2", "3", "99"]:
        candidate = f"{base}{suffix}@example.com"
        if candidate not in used_emails:
            used_emails.add(candidate)
            return candidate
    candidate = f"{base}{random.randint(100, 999)}@example.com"
    used_emails.add(candidate)
    return candidate


def make_phone():
    return "01" + "".join(random.choice(string.digits) for _ in range(9))


def register_user(base_url, payload, timeout=10):
    """POST to backend/register.php. Returns (success: bool, message: str)."""
    url = f"{base_url.rstrip('/')}/backend/register.php"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("success", False), body.get("message", "")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            return False, body.get("message", str(e))
        except Exception:
            return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Create one doctor account per AI-recognized specialty")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL of the deployed app")
    parser.add_argument("--per-specialty", type=int, default=1, help="How many doctors to create per specialty")
    parser.add_argument("--output", default="mediconnect_doctors.csv", help="CSV output filename")
    args = parser.parse_args()

    used_names = set()
    used_emails = set()
    rows = []

    total = len(SPECIALTIES) * args.per_specialty
    print(f"Target: {args.base_url}")
    print(f"Creating {total} doctor account(s) across {len(SPECIALTIES)} specialties...\n")

    count = 0
    for specialty in SPECIALTIES:
        for n in range(1, args.per_specialty + 1):
            count += 1
            name = make_name(used_names)
            email = make_email(name, used_emails)
            password = random_password()
            phone = make_phone()

            payload = {
                "name": name,
                "email": email,
                "password": password,
                "phone": phone,
                "role": "doctor",
                "specialization": specialty,
            }

            success, message = register_user(args.base_url, payload)
            status = "OK" if success else "FAILED"
            print(f"[{status}] {count}/{total}: {name} <{email}> — {specialty} — {message}")

            rows.append({
                "role": "doctor",
                "full_name": name,
                "email": email,
                "password": password,
                "phone": phone,
                "specialization": specialty,
                "status": status,
                "server_message": message,
            })

    fieldnames = ["role", "full_name", "email", "password", "phone", "specialization", "status", "server_message"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_count = sum(1 for r in rows if r["status"] == "OK")
    print(f"\nDone: {ok_count}/{len(rows)} doctor accounts created successfully.")
    print(f"Credentials saved to: {args.output}")
    print("\nSpecialties covered:")
    for s in SPECIALTIES:
        print(f"  - {s}")
    print("\nNote: passwords are stored in plain text in the CSV for your own testing "
          "reference — the app itself only stores the bcrypt hash in the database.")


if __name__ == "__main__":
    main()
