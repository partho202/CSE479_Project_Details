#!/usr/bin/env python3
"""
MediConnect — Automated Deployment Script (Kali / Ubuntu / Debian)

Automates the full setup documented in MEDICONNECT_KALI_FINAL_GUIDE.md:
  1. Fetches the project from GitHub (tries project.zip first, falls back
     to a full `git clone` of the repo if the zip is missing/renamed/moved).
  2. Installs apache2, mariadb-server, php, python3, etc.
  3. Copies the project into /var/www/html/mediconnect with correct
     ownership/permissions.
  4. Fixes MariaDB root auth so PHP's mysqli can connect (matches the
     blank-password config in backend/db.php).
  5. Creates the `mediconnect` database and the `users` / `appointments`
     tables.
  6. Sets up a Python venv for the AI microservice and installs its
     dependencies.
  7. Optionally starts the AI service (ai_api.py) in the background.

USAGE
-----
    sudo python3 deploy_mediconnect.py
    sudo python3 deploy_mediconnect.py --start-ai        # also launch ai_api.py
    sudo python3 deploy_mediconnect.py --repo-url https://github.com/USER/REPO
    sudo python3 deploy_mediconnect.py --skip-packages    # skip apt install
    sudo python3 deploy_mediconnect.py --dest /var/www/html/mediconnect

Must be run as root (it uses apt, systemctl, and writes to /var/www/html).
"""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

DEFAULT_REPO = "https://github.com/partho202/CSE479_Project_Details"
DEFAULT_BRANCH = "main"
DEFAULT_ZIP_NAME = "project.zip"
DEFAULT_DEST = "/var/www/html/mediconnect"
DB_NAME = "mediconnect"

SCHEMA_SQL = """
CREATE DATABASE IF NOT EXISTS mediconnect CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE mediconnect;

CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    full_name       VARCHAR(255)      NOT NULL,
    email           VARCHAR(254)      NOT NULL,
    password        VARCHAR(255)      NOT NULL,
    role            ENUM('patient','doctor','admin') NOT NULL DEFAULT 'patient',
    phone           VARCHAR(50)       NULL,
    specialization  VARCHAR(255)      NULL,
    experience      INT               NULL,
    about           TEXT              NULL,
    date_of_birth   DATE              NULL,
    address         TEXT              NULL,
    profile_image   VARCHAR(255)      NULL,
    created_at      TIMESTAMP         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS appointments (
    id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    patient_id         INT UNSIGNED NOT NULL,
    doctor_id          INT UNSIGNED NOT NULL,
    doctor_name        VARCHAR(255) NOT NULL,
    specialization     VARCHAR(255) NULL,
    appointment_date   DATE         NOT NULL,
    appointment_time   VARCHAR(20)  NOT NULL,
    symptom_details    TEXT         NOT NULL,
    status             VARCHAR(30)  NOT NULL DEFAULT 'Pending',
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_appt_patient FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_appt_doctor  FOREIGN KEY (doctor_id)  REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX IF NOT EXISTS idx_appt_patient ON appointments (patient_id);
CREATE INDEX IF NOT EXISTS idx_appt_doctor  ON appointments (doctor_id);
CREATE INDEX IF NOT EXISTS idx_users_role   ON users (role);
"""

APT_PACKAGES = [
    "apache2", "mariadb-server", "php", "php-mysqli", "php-mbstring",
    "php-cli", "libapache2-mod-php", "python3", "python3-venv",
    "python3-pip", "unzip", "git",
]

PIP_PACKAGES = ["flask", "flask-cors", "joblib", "numpy", "scikit-learn", "pandas"]

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"


def step(msg):
    print(f"\n{CYAN}==> {msg}{RESET}")


def ok(msg):
    print(f"{GREEN}[OK]{RESET} {msg}")


def warn(msg):
    print(f"{YELLOW}[WARN]{RESET} {msg}")


def fail(msg):
    print(f"{RED}[FAIL]{RESET} {msg}")


def run(cmd, check=True, capture=False, cwd=None, env=None):
    """Run a shell command, echoing it first."""
    printable = cmd if isinstance(cmd, str) else " ".join(cmd)
    print(f"    $ {printable}")
    result = subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        check=False,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
    )
    if check and result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout)
        raise RuntimeError(f"Command failed ({result.returncode}): {printable}")
    return result


def require_root():
    if os.geteuid() != 0:
        fail("This script must be run as root, e.g.: sudo python3 deploy_mediconnect.py")
        sys.exit(1)


def command_exists(name):
    return shutil.which(name) is not None


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------

def install_packages(skip):
    step("Installing required packages (apt)")
    if skip:
        warn("Skipped (--skip-packages)")
        return
    run("apt update")
    run(["apt", "install", "-y"] + APT_PACKAGES)
    ok("Packages installed")


def start_services():
    step("Starting and enabling apache2 + mariadb")
    run("systemctl enable --now apache2")
    run("systemctl enable --now mariadb")
    ok("Services enabled and started")


def fetch_project(repo_url, branch, zip_name, work_dir):
    """
    Try to download <repo>/raw/<branch>/<zip_name> first.
    If that fails (404 / renamed / moved), fall back to git-cloning the
    whole repo and using its contents directly.
    Returns the path to the folder that contains index.html (project root).
    """
    step("Fetching project from GitHub")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    repo_url = repo_url.rstrip("/")
    if "github.com" not in repo_url:
        fail(f"--repo-url does not look like a GitHub URL: {repo_url}")
        sys.exit(1)

    raw_base = repo_url.replace("github.com", "raw.githubusercontent.com")
    zip_url = f"{raw_base}/{branch}/{zip_name}"
    zip_path = work_dir / zip_name

    print(f"    Trying direct zip download: {zip_url}")
    try:
        urllib.request.urlretrieve(zip_url, zip_path)
        if zip_path.stat().st_size < 1024:
            raise RuntimeError("Downloaded file too small — probably a 404 page, not a real zip")
        ok(f"Downloaded {zip_name} ({zip_path.stat().st_size // 1024} KB)")
    except Exception as e:
        warn(f"Direct zip download failed ({e})")
        warn("Falling back to `git clone` of the full repository...")
        clone_dir = work_dir / "repo_clone"
        if clone_dir.exists():
            shutil.rmtree(clone_dir)
        run(["git", "clone", "--depth", "1", "--branch", branch, f"{repo_url}.git", str(clone_dir)])

        # Look for a zip anywhere in the cloned repo (name might have changed)
        found_zip = None
        for p in clone_dir.rglob("*.zip"):
            found_zip = p
            break

        if found_zip:
            ok(f"Found zip in cloned repo: {found_zip.name}")
            zip_path = work_dir / found_zip.name
            shutil.copy(found_zip, zip_path)
        else:
            # No zip at all — assume the repo itself contains the project,
            # or a subfolder does (look for index.html)
            warn("No .zip found in the repo either — searching for index.html directly")
            for candidate in clone_dir.rglob("index.html"):
                project_root = candidate.parent
                ok(f"Using project files directly from clone: {project_root}")
                return project_root
            fail("Could not find project.zip OR index.html anywhere in the repo.")
            fail("Please pass --repo-url / --zip-name pointing to the right location,")
            fail("or download the project manually and use --local-zip / --local-dir.")
            sys.exit(1)

    # Extract whatever zip we ended up with
    extract_dir = work_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    step(f"Extracting {zip_path.name}")
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
    except zipfile.BadZipFile:
        fail(f"{zip_path} is not a valid zip file (maybe GitHub renamed/moved it).")
        fail("Re-check the file at: " + repo_url)
        sys.exit(1)

    # The zip may contain a top-level "project/" folder, or the files directly.
    # Find whichever folder actually has index.html.
    for candidate in extract_dir.rglob("index.html"):
        project_root = candidate.parent
        ok(f"Project root detected: {project_root}")
        return project_root

    fail("Extracted the zip but couldn't find index.html anywhere inside it.")
    sys.exit(1)


def deploy_files(project_root, dest):
    step(f"Copying project into {dest}")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    for item in Path(project_root).iterdir():
        target = dest / item.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    run(["chown", "-R", "www-data:www-data", str(dest)])
    run(f"find {dest} -type d -exec chmod 755 {{}} \\;")
    run(f"find {dest} -type f -exec chmod 644 {{}} \\;")

    uploads_dir = dest / "backend" / "uploads"
    if uploads_dir.exists():
        run(["chmod", "-R", "775", str(uploads_dir)])
    else:
        uploads_dir.mkdir(parents=True, exist_ok=True)
        run(["chown", "www-data:www-data", str(uploads_dir)])
        run(["chmod", "775", str(uploads_dir)])

    ok("Project files deployed")


def fix_mysql_auth():
    step("Fixing MariaDB root auth (unix_socket -> password) for PHP mysqli")
    run(["mysql", "-e", "ALTER USER 'root'@'localhost' IDENTIFIED BY ''; FLUSH PRIVILEGES;"], check=False)
    ok("Root auth updated (blank password, matches backend/db.php)")


def create_database():
    step("Creating database + tables")
    run(["mysql", "-e", SCHEMA_SQL])
    result = run(["mysql", "-N", "-e", "SHOW TABLES FROM mediconnect;"], capture=True)
    tables = [t.strip() for t in (result.stdout or "").splitlines() if t.strip()]
    if "users" in tables and "appointments" in tables:
        ok(f"Tables present: {', '.join(tables)}")
    else:
        warn(f"Unexpected table list: {tables}")


def setup_ai_service(dest):
    step("Setting up the AI microservice (Python venv)")
    ai_dir = Path(dest) / "ai"
    if not ai_dir.exists():
        warn(f"No ai/ folder found at {ai_dir} — skipping AI setup")
        return None

    venv_dir = ai_dir / "venv"
    if not venv_dir.exists():
        run(["python3", "-m", "venv", str(venv_dir)])

    pip_bin = venv_dir / "bin" / "pip"
    run([str(pip_bin), "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(pip_bin), "install"] + PIP_PACKAGES)
    ok("AI service dependencies installed")
    return ai_dir


def start_ai_service(ai_dir):
    step("Starting the AI service in the background")
    venv_python = Path(ai_dir) / "venv" / "bin" / "python3"
    log_path = Path(ai_dir) / "ai_api.log"
    with open(log_path, "w") as log_file:
        subprocess.Popen(
            [str(venv_python), "ai_api.py"],
            cwd=str(ai_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    ok(f"AI service launched — logs at {log_path}")
    ok("Check it's up with:  curl http://127.0.0.1:5000/health")


def print_summary(dest, ai_started):
    print(f"\n{GREEN}{'=' * 60}{RESET}")
    print(f"{GREEN}MediConnect deployment complete{RESET}")
    print(f"{GREEN}{'=' * 60}{RESET}")
    print(f"""
Web app:      http://localhost/mediconnect/index.html
Create admin: http://localhost/mediconnect/backend/create_first_admin.php
              (delete backend/create_first_admin.php after creating it)

Deployed to:  {dest}
""")
    if ai_started:
        print("AI service:   already running in the background (http://127.0.0.1:5000)")
    else:
        print(f"""AI service:   not started automatically. To start it manually:
    cd {dest}/ai
    source venv/bin/activate
    python3 ai_api.py
""")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Automated MediConnect deployment for Kali/Ubuntu/Debian")
    parser.add_argument("--repo-url", default=DEFAULT_REPO, help="GitHub repo URL")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="Branch to fetch from")
    parser.add_argument("--zip-name", default=DEFAULT_ZIP_NAME, help="Zip filename to look for in the repo")
    parser.add_argument("--dest", default=DEFAULT_DEST, help="Where to deploy (Apache web root path)")
    parser.add_argument("--work-dir", default="/tmp/mediconnect_deploy", help="Scratch/download directory")
    parser.add_argument("--skip-packages", action="store_true", help="Skip apt package installation")
    parser.add_argument("--skip-ai-setup", action="store_true", help="Skip Python venv / AI setup entirely")
    parser.add_argument("--start-ai", action="store_true", help="Launch ai_api.py in the background after setup")
    parser.add_argument("--local-zip", default=None, help="Use a local project.zip instead of downloading")
    parser.add_argument("--local-dir", default=None, help="Use a local already-extracted project folder instead of downloading")
    args = parser.parse_args()

    require_root()

    print(f"{CYAN}MediConnect automated deployment{RESET}")
    print(f"Target: {args.dest}\n")

    install_packages(args.skip_packages)
    start_services()

    if args.local_dir:
        project_root = Path(args.local_dir)
        for candidate in project_root.rglob("index.html"):
            project_root = candidate.parent
            break
        ok(f"Using local directory: {project_root}")
    elif args.local_zip:
        work_dir = Path(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        extract_dir = work_dir / "extracted_local"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)
        with zipfile.ZipFile(args.local_zip) as z:
            z.extractall(extract_dir)
        project_root = extract_dir
        for candidate in extract_dir.rglob("index.html"):
            project_root = candidate.parent
            break
        ok(f"Extracted local zip: {project_root}")
    else:
        project_root = fetch_project(args.repo_url, args.branch, args.zip_name, args.work_dir)

    deploy_files(project_root, args.dest)
    fix_mysql_auth()
    create_database()

    ai_dir = None
    if not args.skip_ai_setup:
        ai_dir = setup_ai_service(args.dest)

    ai_started = False
    if args.start_ai and ai_dir:
        start_ai_service(ai_dir)
        ai_started = True

    print_summary(args.dest, ai_started)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        fail(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        warn("Interrupted by user")
        sys.exit(130)
