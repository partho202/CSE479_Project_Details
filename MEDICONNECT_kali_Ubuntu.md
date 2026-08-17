# MediConnect — Kali Linux Deployment Guide (Final)

This is the final, working setup based on what was actually run on this machine (Kali Linux, MariaDB, root with blank password, Python venv for the AI service).

---

## 1. Install required packages

```bash
sudo apt update
sudo apt install -y apache2 mariadb-server php php8.4-mysql php-mbstring php-cli libapache2-mod-php python3 python3-venv python3-pip unzip
```

## 2. Start and enable services

```bash
sudo systemctl enable --now apache2
sudo systemctl enable --now mariadb
```

Check they're running:

```bash
systemctl status apache2 --no-pager
systemctl status mariadb --no-pager
```

## 3. Copy the project into Apache's web root

```bash
sudo mkdir -p /var/www/html/mediconnect
sudo cp -r /home/kali/Downloads/project/* /var/www/html/mediconnect/
sudo chown -R www-data:www-data /var/www/html/mediconnect
sudo find /var/www/html/mediconnect -type d -exec chmod 755 {} \;
sudo find /var/www/html/mediconnect -type f -exec chmod 644 {} \;
sudo chmod -R 775 /var/www/html/mediconnect/backend/uploads
```

## 4. Fix MySQL root auth (so PHP can connect)

Kali's MariaDB root defaults to `unix_socket` auth, which blocks PHP's `mysqli`. This switches root to password auth with a blank password, matching `db.php`:

```bash
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY ''; FLUSH PRIVILEGES;"
```

## 5. Create the database

```bash
sudo mysql -e "CREATE DATABASE IF NOT EXISTS mediconnect CHARACTER SET utf8mb4;"
sudo mysql -e "SHOW DATABASES LIKE 'mediconnect';"
```

## 6. Create the tables

```bash
sudo mysql mediconnect
```

Paste this inside the MariaDB prompt:

```sql
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

CREATE INDEX idx_appt_patient ON appointments (patient_id);
CREATE INDEX idx_appt_doctor  ON appointments (doctor_id);
CREATE INDEX idx_users_role   ON users (role);
```

Verify, then exit:

```sql
SHOW TABLES;
EXIT;
```

## 7. Create the first admin account

Open in browser:

```
http://localhost/mediconnect/backend/create_first_admin.php
```

Fill the form and submit. Then delete the file so no one else can use it:

```bash
sudo rm /var/www/html/mediconnect/backend/create_first_admin.php
```

## 8. Set up the AI service (Python)

```bash
cd /var/www/html/mediconnect/ai
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
pip install flask flask-cors joblib numpy scikit-learn pandas
python3 ai_api.py
```

Confirms it's working when you see:
```
Model loaded successfully.
Symptoms loaded: 377
Starting MediConnect AI API...
URL: http://127.0.0.1:5000
```

(`InconsistentVersionWarning` lines are harmless — just a scikit-learn version note.)

## 9. Open the site

```
http://localhost/mediconnect/index.html
```

---

# ▶️ How to START (every time you use the app)

Open **two terminals**.

**Terminal 1 — web server + database:**
```bash
sudo systemctl start apache2
sudo systemctl start mariadb
```

**Terminal 2 — AI service:**
```bash
cd /var/www/html/mediconnect/ai
source venv/bin/activate
python3 ai_api.py
```

Leave Terminal 2 open the whole time you're using the chat/symptom-checker feature.

Then open the browser:
```
http://localhost/mediconnect/index.html
```

---

# ⏹ How to STOP

**Stop the AI service (Terminal 2):**

Press `Ctrl+C` in that terminal.

**Stop Apache and MariaDB:**
```bash
sudo systemctl stop apache2
sudo systemctl stop mariadb
```

**If port 5000 is stuck / AI service won't restart cleanly:**
```bash
sudo fuser -k 5000/tcp
```
Then run `python3 ai_api.py` again.

**Check nothing is still running on port 5000:**
```bash
sudo ss -ltnp | grep ':5000' || echo "Port 5000 is free"
```

---

## Quick reference — full status check

```bash
systemctl status apache2 --no-pager
systemctl status mariadb --no-pager
sudo ss -ltnp | grep ':5000' || echo "AI service not running"
```
