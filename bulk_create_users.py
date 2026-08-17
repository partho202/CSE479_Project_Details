#!/usr/bin/env python3
"""
bulk_create_users.py — MediConnect test-data generator

Creates 10 patient accounts and 7 doctor accounts by calling the real
backend/register.php API (so passwords go through the app's normal
password_hash() flow, exactly like a real signup). Saves every
generated name/email/password/role to a CSV file for reference.

USAGE
-----
    python3 bulk_create_users.py
    python3 bulk_create_users.py --base-url http://localhost/mediconnect
    python3 bulk_create_users.py --patients 15 --doctors 5
    python3 bulk_create_users.py --output my_accounts.csv

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
# Sample data pools
# --------------------------------------------------------------------------

FIRST_NAMES = [
    "Rafiq", "Nusrat", "Kamal", "Farzana", "Shakil", "Mitu", "Tanvir",
    "Sadia", "Imran", "Nabila", "Rakib", "Sumaiya", "Hasan", "Priya",
    "Arif", "Lamia", "Junaid", "Tania", "Rezaul", "Mahin",
]

LAST_NAMES = [
    "Ahmed", "Islam", "Hossain", "Rahman", "Chowdhury", "Karim", "Akter",
    "Hasan", "Uddin", "Khan", "Sultana", "Alam",
]

SPECIALIZATIONS = [
    "Cardiology", "Dermatology", "Neurology", "Orthopedics",
    "Pediatrics", "General Medicine", "ENT", "Psychiatry",
    "Gynecology", "Ophthalmology",
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
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in used_names:
            used_names.add(name)
            return name


def make_email(name, used_emails):
    base = name.lower().replace(" ", ".")
    for suffix in ["", "1", "2", "3", "99"]:
        candidate = f"{base}{suffix}@example.com"
        if candidate not in used_emails:
            used_emails.add(candidate)
            return candidate
    # fallback for the unlikely collision case
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
    parser = argparse.ArgumentParser(description="Bulk-create MediConnect patient/doctor accounts")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL of the deployed app")
    parser.add_argument("--patients", type=int, default=10, help="Number of patient accounts to create")
    parser.add_argument("--doctors", type=int, default=7, help="Number of doctor accounts to create")
    parser.add_argument("--output", default="mediconnect_accounts.csv", help="CSV output filename")
    args = parser.parse_args()

    used_names = set()
    used_emails = set()
    rows = []

    print(f"Target: {args.base_url}")
    print(f"Creating {args.patients} patients and {args.doctors} doctors...\n")

    # -------- Patients --------
    for i in range(1, args.patients + 1):
        name = make_name(used_names)
        email = make_email(name, used_emails)
        password = random_password()
        phone = make_phone()

        payload = {
            "name": name,
            "email": email,
            "password": password,
            "phone": phone,
            "role": "patient",
        }

        success, message = register_user(args.base_url, payload)
        status = "OK" if success else "FAILED"
        print(f"[{status}] Patient {i}/{args.patients}: {name} <{email}> — {message}")

        rows.append({
            "role": "patient",
            "full_name": name,
            "email": email,
            "password": password,
            "phone": phone,
            "specialization": "",
            "status": status,
            "server_message": message,
        })

    # -------- Doctors --------
    for i in range(1, args.doctors + 1):
        name = make_name(used_names)
        email = make_email(name, used_emails)
        password = random_password()
        phone = make_phone()
        specialization = random.choice(SPECIALIZATIONS)

        payload = {
            "name": name,
            "email": email,
            "password": password,
            "phone": phone,
            "role": "doctor",
            "specialization": specialization,
        }

        success, message = register_user(args.base_url, payload)
        status = "OK" if success else "FAILED"
        print(f"[{status}] Doctor {i}/{args.doctors}: {name} <{email}> ({specialization}) — {message}")

        rows.append({
            "role": "doctor",
            "full_name": name,
            "email": email,
            "password": password,
            "phone": phone,
            "specialization": specialization,
            "status": status,
            "server_message": message,
        })

    # -------- Save CSV --------
    fieldnames = ["role", "full_name", "email", "password", "phone", "specialization", "status", "server_message"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_count = sum(1 for r in rows if r["status"] == "OK")
    print(f"\nDone: {ok_count}/{len(rows)} accounts created successfully.")
    print(f"Credentials saved to: {args.output}")
    print("\nNote: passwords are stored in plain text in the CSV for your own testing "
          "reference — the app itself only stores the bcrypt hash in the database.")


if __name__ == "__main__":
    main()
