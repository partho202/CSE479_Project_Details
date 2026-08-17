# MediConnect — LAN Access Fix (Full Resolution Log)

This document records the full process of making MediConnect (running inside a Kali Linux VM on VMware) accessible from **any device on the same room/WiFi network**, not just from inside the VM itself.

---

## The Problem

The app loaded fine at `http://192.168.1.8/mediconnect/index.html` from another laptop — the PHP/Apache/MySQL part worked immediately over LAN. But the AI chat widget showed:

```
The AI service is unavailable.
Please make sure python ai_api.py is running on http://127.0.0.1:5000.
```

**Root cause:** two separate issues stacked on top of each other:

1. `ai_api.py` was hardcoded to `host="127.0.0.1"`, which only accepts connections from *inside the same machine* — not from other devices on the network.
2. The frontend (`index.html`, `patient/js/patient.js`) was hardcoded to call `http://127.0.0.1:5000`. On another laptop's browser, `127.0.0.1` means *that laptop itself*, not the Kali VM — so even after fixing #1, the browser was calling the wrong address entirely.

---

## Step 1 — Find the VM's LAN IP address

```bash
ip a | grep "inet " | grep -v 127.0.0.1
```

Result: `192.168.1.8` (this must be reachable from other devices — see [Networking Prerequisite](#networking-prerequisite-bridged-mode) below).

---

## Step 2 — Check how ai_api.py binds

```bash
grep -n "app.run\|127.0.0.1" /var/www/html/mediconnect/ai/ai_api.py
```

Output showed:
```
736:        "URL: http://127.0.0.1:5000"
740:    app.run(
741:        host="127.0.0.1",
```

Confirmed: Flask was only listening on the loopback interface.

---

## Step 3 — Make Flask listen on all interfaces

```bash
sudo sed -i 's/127\.0\.0\.1/0.0.0.0/g' /var/www/html/mediconnect/ai/ai_api.py
```

Verified:
```bash
sed -n '738,745p' /var/www/html/mediconnect/ai/ai_api.py
```

`host="127.0.0.1"` became `host="0.0.0.0"` — Flask now accepts connections on any network interface, not just localhost.

---

## Step 4 — Point the frontend at the VM's real IP

```bash
sudo sed -i 's/127\.0\.0\.1:5000/192.168.1.8:5000/g' /var/www/html/mediconnect/index.html
sudo sed -i 's/127\.0\.0\.1:5000/192.168.1.8:5000/g' /var/www/html/mediconnect/patient/js/patient.js
```

Now any browser on the LAN calls `http://192.168.1.8:5000/recommend` — the VM's real, network-reachable address — instead of its own loopback.

---

## Step 5 — Firewall check

```bash
sudo ufw status
```

Result: `ufw: command not found` → **no firewall installed at all**, so nothing was blocking port 5000 or port 80. This step turned out to be unnecessary on this machine (skip it if you get the same "command not found").

---

## Step 6 — Restart the AI service (and clear the port conflict)

First restart attempt failed:
```
Address already in use
Port 5000 is in use by another program.
```

Cause: an old copy of `ai_api.py` (still bound to `127.0.0.1` from before the fix) was left running in the background from an earlier terminal session.

**Fix — kill whatever's holding port 5000:**
```bash
sudo fuser -k 5000/tcp
```

**Then start fresh:**
```bash
cd /var/www/html/mediconnect/ai
source venv/bin/activate
python3 ai_api.py
```

Confirmed working output:
```
URL: http://0.0.0.0:5000
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.1.8:5000
```

---

## Step 7 — Verify from another device

On a different laptop's browser, hard-refresh the page (`Ctrl+Shift+R`) to clear any cached JS, then:

```
http://192.168.1.8/mediconnect/index.html
```

Opened the AI chat widget and sent a message — response came back successfully. **LAN access confirmed working.**

---

## Networking Prerequisite: Bridged Mode

For a VM to be reachable from other physical devices on the room's WiFi/LAN at all, VMware's network adapter must be set to **Bridged**, not the default NAT mode:

- VMware Player → **Player menu → Manage → Virtual Machine Settings → Network Adapter → Bridged**
- Restart the VM after changing this.

(In this case it was already working, but this is the setting to check first if `http://<VM-IP>/...` doesn't load from another device at all.)

---

## Summary of All Changes Made

| File | Change |
|---|---|
| `ai/ai_api.py` | `host="127.0.0.1"` → `host="0.0.0.0"` (Flask now listens on all network interfaces) |
| `index.html` | `http://127.0.0.1:5000` → `http://192.168.1.8:5000` |
| `patient/js/patient.js` | `http://127.0.0.1:5000` → `http://192.168.1.8:5000` |

---

## ⚠️ Important Caveat: IP Address Can Change

`192.168.1.8` is only guaranteed until the VM's network reconnects (VM restart, WiFi reconnect, router DHCP renewal, etc.). If the AI chat stops working again after a reboot:

**1. Check the current IP:**
```bash
ip a | grep "inet " | grep -v 127.0.0.1
```

**2. If it changed, redo Step 4 with the new IP:**
```bash
sudo sed -i 's/192\.168\.1\.8:5000/<NEW-IP>:5000/g' /var/www/html/mediconnect/index.html
sudo sed -i 's/192\.168\.1\.8:5000/<NEW-IP>:5000/g' /var/www/html/mediconnect/patient/js/patient.js
```

(For a permanent fix, set a **static IP / DHCP reservation** for the Kali VM in your router settings so this never has to be redone.)

---

## Daily Start Routine (LAN-ready)

```bash
sudo systemctl start apache2
sudo systemctl start mariadb

cd /var/www/html/mediconnect/ai
source venv/bin/activate
python3 ai_api.py
```

Then, from any device on the same network:
```
http://192.168.1.8/mediconnect/index.html
```

---

## Quick Troubleshooting Reference

| Symptom | Cause | Fix |
|---|---|---|
| "AI service unavailable" from another device, but works on the VM itself | Flask bound to `127.0.0.1` only | Step 3 |
| Chat still fails after Step 3 | Frontend still hardcoded to `127.0.0.1:5000` | Step 4 |
| `Address already in use` on restart | Old `ai_api.py` process still running | `sudo fuser -k 5000/tcp`, then restart |
| Page doesn't load at all from another device (`http://<VM-IP>/...`) | VM network adapter not in Bridged mode | See [Networking Prerequisite](#networking-prerequisite-bridged-mode) |
| Worked yesterday, broken today | VM's IP address changed | See [IP Address Can Change](#️-important-caveat-ip-address-can-change) |
