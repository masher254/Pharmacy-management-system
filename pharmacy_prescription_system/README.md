# Pharmacy Online Prescription Management System

A runnable Flask + SQLite school-project implementation based on the Chapter Two design: login and role-based access, dashboard, prescription management, inventory/batch/expiry tracking, reports and audit logs.

## Requirements
- Python 3.10 or newer
- Visual Studio Code (recommended)
- Python extension for VS Code

## Run on Windows
1. Extract this ZIP to a folder.
2. Open that folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, use `.\.venv\Scripts\activate.bat` in Command Prompt, or run `py -m pip install -r requirements.txt` without activating.
5. Install dependencies:
   ```powershell
   py -m pip install -r requirements.txt
   ```
6. Start the app:
   ```powershell
   py app.py
   ```
7. Open `http://127.0.0.1:5000` in your browser.

The SQLite database (`pharmacy.db`) is created automatically the first time the app runs.

## Patient involvement
Patients can select **Create a patient account** on the login page, register with a name and username, then sign in to their own portal. They can submit a prescription request and track its status. Patients cannot access staff inventory controls, reports, other patients' records, or change prescription status. Requests remain pending until pharmacy staff review them.

## Demonstration accounts
- Administrator: `admin` / `Admin123!`
- Pharmacy Staff: `staff` / `Staff123!`
- Manager: `manager` / `Manager123!`

Change these demo passwords and set a strong `SECRET_KEY` before any real deployment. These are demo credentials only.

## Main features
- Secure password hashing and session login
- Role-based routes for Administrator, Pharmacy Staff, Manager and Patient
- Patient self-registration and a separate patient portal
- Patients can submit prescription requests and view only requests linked to their account
- Dashboard counts for pending/processing/ready prescriptions and low stock
- Create, search and update prescription status
- Inventory batch, expiry date, quantity and reorder-level tracking
- Reports with prescription status totals, inventory value, expired stock count and recent audit events
- Administrator can create user accounts
- Audit log for important actions

## Project structure
```text
pharmacy_prescription_system/
├── app.py
├── requirements.txt
├── README.md
├── pharmacy.db          # generated at first run
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── prescriptions.html
│   ├── prescription_form.html
│   ├── inventory.html
│   ├── inventory_form.html
│   ├── reports.html
│   └── users.html
└── static/
    └── style.css
```

## Important scope note
This is an educational prototype, not a certified clinical or production pharmacy platform. It does not verify prescriptions with a licensed prescriber, connect to a national health system, or provide regulatory compliance certification. Use fictional patient data for demonstrations. Before real use, add HTTPS, CSRF protection, password reset and lockout, backups, stronger audit controls, privacy review and pharmacy/legal validation.
