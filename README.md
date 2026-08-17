# MediConnect

MediConnect is a web-based healthcare platform that connects **patients**, **doctors**, and **admins**, with an integrated **AI-powered symptom checker** that recommends which medical specialty a patient should book an appointment with.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [System Architecture Diagram](#system-architecture-diagram)
- [Core Modules](#core-modules)
- [Database Schema](#database-schema)
- [AI Microservice](#ai-microservice)
- [Authentication & Roles](#authentication--roles)
- [API Reference](#api-reference)
- [Setup](#setup)

---

## Architecture Overview

MediConnect is a **two-service architecture**:

1. **Web application (PHP + MySQL/MariaDB)** — served by Apache, handles authentication, user roles, appointment booking, and admin management. Uses server-rendered PHP pages with `$_SESSION`-based auth and `mysqli` for the database.
2. **AI microservice (Python + Flask)** — a standalone REST API (`ai/ai_api.py`) that takes a natural-language symptom description and returns a recommended medical specialty, using a pre-trained `scikit-learn` (`ExtraTreesClassifier`) model. It runs independently on port `5000` and is called client-side (via `fetch`) from the browser — it is **not** proxied through PHP.

```
Browser (HTML/CSS/JS)
   │
   ├── PHP pages (Apache) ──► MySQL/MariaDB  (users, appointments)
   │
   └── fetch() ──► Flask AI API (127.0.0.1:5000) ──► disease_model.pkl
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, vanilla JavaScript |
| Backend | PHP 8 (procedural, `mysqli`) |
| Database | MySQL / MariaDB |
| Web server | Apache (via XAMPP or native LAMP) |
| AI service | Python 3, Flask, scikit-learn, pandas, joblib |
| ML model | `ExtraTreesClassifier` trained on a symptom–disease dataset |

---

## Project Structure

```
project/
├── index.html              # Public landing page + AI symptom-checker widget
├── login.html               # Login page
├── register.html            # Patient/doctor registration page
│
├── css/                      # Stylesheets
│   ├── style.css             # Global/landing page styles
│   ├── login.css
│   ├── patient.css
│   └── doctor.css
│
├── js/                        # Frontend JS shared by public pages
│   ├── script.js              # Landing page interactions
│   ├── login.js                # Login/register form handling, role-based redirect
│   └── chat.js                 # Public-facing AI chat widget logic
│
├── backend/                    # PHP API layer — session auth, CRUD (JSON responses)
│   ├── db.php                   # mysqli connection (host/user/pass/dbname)
│   ├── login.php                 # Authenticates user, starts $_SESSION
│   ├── logout.php                 # Destroys session
│   ├── register.php                # Creates patient/doctor accounts
│   ├── profile.php                  # Get/update logged-in user's profile
│   ├── upload_profile.php            # Handles profile picture uploads
│   ├── book_appointment.php           # Creates a new appointment record
│   ├── admin_users.php                 # Admin: list/manage users
│   ├── create_first_admin.php           # One-time bootstrap: creates the first admin
│   └── uploads/                          # Stored profile images
│
├── patient/                      # Patient-facing pages (role-gated via $_SESSION)
│   ├── dashboard.php
│   ├── doctors.php                 # Browse/search doctors
│   ├── appointments.php             # List patient's appointments
│   ├── appointment_details.php       # Single appointment view
│   ├── profile.php
│   └── js/
│       ├── patient.js                 # Calls AI /recommend endpoint
│       ├── doctors.js
│       └── appointment.js
│
├── doctor/                        # Doctor-facing pages
│   ├── dashboard.php
│   ├── appointments.php              # View & confirm/manage appointments
│   ├── patient_details.php
│   ├── profile.php
│   └── js/
│       └── doctor.js
│
├── admin/                          # Admin-facing pages
│   ├── admin.php
│   ├── dashboard.php
│   ├── doctors.php
│   ├── patients.php
│   └── js/
│       └── admin.js
│
└── ai/                              # Standalone AI microservice (Flask)
    ├── ai_api.py                     # REST API: symptom extraction + prediction
    ├── train_model.py                 # Trains the ExtraTreesClassifier from dataset.csv
    ├── dataset.csv                     # Symptom–disease training dataset
    ├── disease_model.pkl                # Pre-trained model (loaded at runtime)
    └── symptoms.pkl                      # Serialized list of known symptom columns
```

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                            Browser                                │
│   index.html / login.html / register.html / role dashboards       │
└───────────────┬─────────────────────────────┬─────────────────────┘
                │ HTTP (session cookie)          │ fetch() JSON
                ▼                                 ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│        Apache + PHP            │   │      Flask AI microservice     │
│  /backend/*.php (auth, CRUD)   │   │      ai/ai_api.py :5000        │
│  /patient/*.php  /doctor/*.php │   │  /            → status         │
│  /admin/*.php                  │   │  /health      → health check    │
│                                 │   │  /recommend   → symptom → dept  │
└───────────────┬─────────────────┘   └───────────────┬─────────────────┘
                │ mysqli                                │ joblib.load()
                ▼                                        ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│      MySQL / MariaDB           │   │  disease_model.pkl             │
│  mediconnect.users              │   │  symptoms.pkl                  │
│  mediconnect.appointments       │   │  (ExtraTreesClassifier)        │
└───────────────────────────────┘   └───────────────────────────────┘
```

---

## Core Modules

### 1. Public site (`index.html`, `login.html`, `register.html`)
Landing page, marketing content, and an embedded AI symptom-checker chat widget that calls the Flask API directly at `http://127.0.0.1:5000/recommend`.

### 2. Auth (`backend/login.php`, `register.php`, `logout.php`)
- `register.php` — creates a `users` row with a `role` of `patient` or `doctor`.
- `login.php` — verifies credentials, starts a PHP session (`$_SESSION['user_id']`, `role`, etc.), used by every role-gated page to authorize access.
- `logout.php` — destroys the session.

### 3. Role dashboards (`patient/`, `doctor/`, `admin/`)
Each folder is a self-contained set of PHP pages gated by `$_SESSION['role']`, rendering data pulled live from MySQL (appointments, profiles, doctor listings, etc.).

### 4. Appointment system (`backend/book_appointment.php`, `patient/appointments.php`, `doctor/appointments.php`)
Patients book appointments against a doctor; doctors can view/confirm/manage the appointments assigned to them. Status flows through values like `Pending` → `Confirmed`.

### 5. AI symptom checker (`ai/`)
A Flask REST API, independent of PHP, that:
1. Extracts recognizable symptoms from free-text input (`extract_symptoms`).
2. Runs them through a pre-trained `ExtraTreesClassifier` (`predict_disease`).
3. Maps the predicted disease/symptoms to a recommended medical specialty (`get_recommended_specialty`).
4. Flags potential emergencies in the input text (`detect_emergency`).

---

## Database Schema

```sql
users (
  id, full_name, email, password, role ENUM('patient','doctor','admin'),
  phone, specialization, experience, about, date_of_birth,
  address, profile_image, created_at
)

appointments (
  id, patient_id, doctor_id, doctor_name, specialization,
  appointment_date, appointment_time, symptom_details,
  status, created_at
)
```

`appointments.patient_id` and `appointments.doctor_id` are foreign keys into `users.id`.

---

## AI Microservice

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Service status, symptom/disease class counts |
| `/health` | GET | Health check (model loaded, symptom count) |
| `/recommend` | POST | Body: `{ "message": "<free text symptoms>" }` → returns detected symptoms, recommended specialty, emergency flag |

The model is pre-trained (`disease_model.pkl` + `symptoms.pkl` ship with the repo); `train_model.py` can be re-run against `dataset.csv` to regenerate them.

---

## Authentication & Roles

Session-based auth via native PHP `$_SESSION`, set on login:

```php
$_SESSION["user_id"]
$_SESSION["user_name"]
$_SESSION["user_email"]
$_SESSION["role"]   // 'patient' | 'doctor' | 'admin'
```

Every page under `patient/`, `doctor/`, and `admin/` checks `$_SESSION['role']` before rendering, redirecting unauthorized users back to `login.html`.

---

## Setup

See the deployment guides in this repo for full step-by-step instructions (Windows/XAMPP and Linux/LAMP), including database schema import and running the AI microservice alongside Apache.
