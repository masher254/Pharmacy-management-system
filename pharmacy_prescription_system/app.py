from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date
import sqlite3, os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "pharmacy.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-development-secret-key")

ROLES = ("Administrator", "Pharmacy Staff", "Manager", "Patient")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('Administrator','Pharmacy Staff','Manager')),
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prescription_code TEXT UNIQUE NOT NULL,
        patient_name TEXT NOT NULL,
        patient_contact TEXT DEFAULT '',
        prescriber_name TEXT DEFAULT '',
        medicine_name TEXT NOT NULL,
        dosage TEXT DEFAULT '',
        quantity INTEGER NOT NULL DEFAULT 1,
        notes TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Pending'
            CHECK(status IN ('Pending','Processing','Ready for Collection','Collected','Rejected')),
        created_by INTEGER,
        patient_user_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id),
        FOREIGN KEY(patient_user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_name TEXT NOT NULL,
        batch_number TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        reorder_level INTEGER NOT NULL DEFAULT 10,
        expiry_date TEXT NOT NULL,
        unit_price REAL NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        UNIQUE(medicine_name, batch_number)
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    # Lightweight migrations for databases created by an earlier version of this demo.
    user_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()["sql"]
    if "'Patient'" not in user_sql and '"Patient"' not in user_sql:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript("""
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Administrator','Pharmacy Staff','Manager','Patient')),
            created_at TEXT NOT NULL
        );
        INSERT INTO users_new(id,username,password_hash,full_name,role,created_at)
        SELECT id,username,password_hash,full_name,role,created_at FROM users;
        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;
        """)
        conn.execute("PRAGMA foreign_keys = ON")
    prescription_cols = {row["name"] for row in conn.execute("PRAGMA table_info(prescriptions)").fetchall()}
    if "patient_user_id" not in prescription_cols:
        conn.execute("ALTER TABLE prescriptions ADD COLUMN patient_user_id INTEGER REFERENCES users(id)")
    count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count == 0:
        now = datetime.now().isoformat(timespec="seconds")
        demo_users = [
            ("admin", generate_password_hash("Admin123!"), "System Administrator", "Administrator", now),
            ("staff", generate_password_hash("Staff123!"), "Pharmacy Staff", "Pharmacy Staff", now),
            ("manager", generate_password_hash("Manager123!"), "Pharmacy Manager", "Manager", now),
        ]
        conn.executemany("INSERT INTO users(username,password_hash,full_name,role,created_at) VALUES(?,?,?,?,?)", demo_users)
    conn.commit()
    conn.close()

def audit(action, details=""):
    if "user_id" not in session:
        return
    conn = get_db()
    conn.execute("INSERT INTO audit_logs(user_id,username,action,details,created_at) VALUES(?,?,?,?,?)",
                 (session["user_id"], session["username"], action, details, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def roles_required(*allowed):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in allowed:
                flash("Your account does not have permission to access that page.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator

@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year, "today": date.today().isoformat()}

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/patient/register", methods=["GET", "POST"])
def patient_register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        contact = request.form.get("contact", "").strip()
        if not full_name or not username or len(password) < 8:
            flash("Enter your full name, username, and a password of at least 8 characters.", "error")
            return render_template("patient_register.html")
        conn = get_db()
        try:
            conn.execute("INSERT INTO users(username,password_hash,full_name,role,created_at) VALUES(?,?,?,?,?)",
                         (username, generate_password_hash(password), full_name, "Patient",
                          datetime.now().isoformat(timespec="seconds")))
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            conn.close()
            session.clear()
            session.update(user_id=user["id"], username=user["username"], full_name=user["full_name"], role=user["role"])
            session["patient_contact"] = contact
            audit("Patient registration", "Patient account created")
            return redirect(url_for("patient_portal"))
        except sqlite3.IntegrityError:
            conn.close()
            flash("That username is already in use. Please choose another.", "error")
    return render_template("patient_register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["id"], username=user["username"], full_name=user["full_name"], role=user["role"])
            audit("Login", "User signed in")
            if user["role"] == "Patient":
                return redirect(url_for("patient_portal"))
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    audit("Logout", "User signed out")
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "Patient":
        return redirect(url_for("patient_portal"))
    conn = get_db()
    stats = {
        "pending": conn.execute("SELECT COUNT(*) n FROM prescriptions WHERE status='Pending'").fetchone()["n"],
        "processing": conn.execute("SELECT COUNT(*) n FROM prescriptions WHERE status='Processing'").fetchone()["n"],
        "ready": conn.execute("SELECT COUNT(*) n FROM prescriptions WHERE status='Ready for Collection'").fetchone()["n"],
        "low_stock": conn.execute("SELECT COUNT(*) n FROM inventory WHERE quantity <= reorder_level").fetchone()["n"],
        "prescriptions": conn.execute("SELECT * FROM prescriptions ORDER BY created_at DESC LIMIT 6").fetchall(),
        "low_items": conn.execute("SELECT * FROM inventory WHERE quantity <= reorder_level ORDER BY quantity ASC LIMIT 6").fetchall()
    }
    conn.close()
    return render_template("dashboard.html", stats=stats)

@app.route("/prescriptions")
@login_required
def prescriptions():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    conn = get_db()
    if session.get("role") == "Patient":
        sql = """SELECT * FROM prescriptions WHERE patient_user_id = ?
                 AND (prescription_code LIKE ? OR patient_name LIKE ? OR medicine_name LIKE ?)"""
        args = [session["user_id"], f"%{q}%", f"%{q}%", f"%{q}%"]
    else:
        sql = "SELECT * FROM prescriptions WHERE (prescription_code LIKE ? OR patient_name LIKE ? OR medicine_name LIKE ?)"
        args = [f"%{q}%", f"%{q}%", f"%{q}%"]
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return render_template("prescriptions.html", prescriptions=rows, q=q, selected_status=status)

@app.route("/prescriptions/new", methods=["GET", "POST"])
@login_required
@roles_required("Administrator", "Pharmacy Staff", "Patient")
def prescription_new():
    if request.method == "POST":
        form = request.form
        code = "RX-" + datetime.now().strftime("%y%m%d%H%M%S")
        now = datetime.now().isoformat(timespec="seconds")
        try:
            conn = get_db()
            is_patient = session.get("role") == "Patient"
            patient_name = session.get("full_name") if is_patient else form.get("patient_name","").strip()
            patient_contact = session.get("patient_contact", "") if is_patient else form.get("patient_contact","").strip()
            patient_user_id = session["user_id"] if is_patient else None
            conn.execute("""INSERT INTO prescriptions
                (prescription_code,patient_name,patient_contact,prescriber_name,medicine_name,dosage,quantity,notes,status,created_by,patient_user_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (code, patient_name, patient_contact,
                 form.get("prescriber_name","").strip(), form.get("medicine_name","").strip(),
                 form.get("dosage","").strip(), int(form.get("quantity","1")), form.get("notes","").strip(),
                 "Pending", session["user_id"], patient_user_id, now, now))
            conn.commit()
            conn.close()
            audit("Create prescription", f"{code} for {form.get('patient_name','').strip()}")
            flash(f"Prescription request {code} submitted.", "success")
            return redirect(url_for("patient_portal") if is_patient else url_for("prescriptions"))
        except (sqlite3.Error, ValueError) as exc:
            flash("Could not save prescription. Check that all required fields are valid.", "error")
    return render_template("prescription_form.html")

@app.route("/prescriptions/<int:prescription_id>/status", methods=["POST"])
@login_required
@roles_required("Administrator", "Pharmacy Staff")
def prescription_status(prescription_id):
    status = request.form.get("status", "")
    allowed = {"Pending", "Processing", "Ready for Collection", "Collected", "Rejected"}
    if status not in allowed:
        flash("Invalid prescription status.", "error")
        return redirect(url_for("prescriptions"))
    conn = get_db()
    row = conn.execute("SELECT prescription_code FROM prescriptions WHERE id=?", (prescription_id,)).fetchone()
    if row:
        conn.execute("UPDATE prescriptions SET status=?, updated_at=? WHERE id=?",
                     (status, datetime.now().isoformat(timespec="seconds"), prescription_id))
        conn.commit()
    conn.close()
    if row:
        audit("Update prescription status", f"{row['prescription_code']} changed to {status}")
        flash("Prescription status updated.", "success")
    return redirect(url_for("prescriptions"))

@app.route("/patient")
@login_required
@roles_required("Patient")
def patient_portal():
    conn = get_db()
    rows = conn.execute("SELECT * FROM prescriptions WHERE patient_user_id=? ORDER BY created_at DESC",
                        (session["user_id"],)).fetchall()
    conn.close()
    return render_template("patient_portal.html", prescriptions=rows)

@app.route("/inventory")
@login_required
@roles_required("Administrator", "Pharmacy Staff", "Manager")
def inventory():
    q = request.args.get("q", "").strip()
    conn = get_db()
    rows = conn.execute("""SELECT * FROM inventory WHERE medicine_name LIKE ? OR batch_number LIKE ?
                           ORDER BY expiry_date ASC""", (f"%{q}%", f"%{q}%")).fetchall()
    conn.close()
    return render_template("inventory.html", items=rows, q=q)

@app.route("/inventory/new", methods=["GET", "POST"])
@login_required
@roles_required("Administrator", "Pharmacy Staff")
def inventory_new():
    if request.method == "POST":
        f = request.form
        try:
            conn = get_db()
            conn.execute("""INSERT INTO inventory(medicine_name,batch_number,quantity,reorder_level,expiry_date,unit_price,updated_at)
                            VALUES(?,?,?,?,?,?,?)""",
                         (f["medicine_name"].strip(), f["batch_number"].strip(), int(f["quantity"]),
                          int(f["reorder_level"]), f["expiry_date"], float(f["unit_price"]),
                          datetime.now().isoformat(timespec="seconds")))
            conn.commit()
            conn.close()
            audit("Add inventory", f"{f['medicine_name']} batch {f['batch_number']}")
            flash("Medicine batch added to inventory.", "success")
            return redirect(url_for("inventory"))
        except (sqlite3.Error, ValueError, KeyError):
            flash("Could not add item. The medicine/batch may already exist or a value is invalid.", "error")
    return render_template("inventory_form.html")

@app.route("/inventory/<int:item_id>/update", methods=["POST"])
@login_required
@roles_required("Administrator", "Pharmacy Staff")
def inventory_update(item_id):
    try:
        quantity = int(request.form.get("quantity", "0"))
        reorder_level = int(request.form.get("reorder_level", "10"))
        if quantity < 0 or reorder_level < 0:
            raise ValueError()
        conn = get_db()
        item = conn.execute("SELECT medicine_name,batch_number FROM inventory WHERE id=?", (item_id,)).fetchone()
        conn.execute("UPDATE inventory SET quantity=?,reorder_level=?,updated_at=? WHERE id=?",
                     (quantity, reorder_level, datetime.now().isoformat(timespec="seconds"), item_id))
        conn.commit()
        conn.close()
        if item:
            audit("Update stock", f"{item['medicine_name']} batch {item['batch_number']}: quantity {quantity}")
        flash("Stock details updated.", "success")
    except ValueError:
        flash("Quantity and reorder level must be non-negative whole numbers.", "error")
    return redirect(url_for("inventory"))

@app.route("/reports")
@login_required
@roles_required("Administrator", "Manager")
def reports():
    conn = get_db()
    status_rows = conn.execute("SELECT status, COUNT(*) AS total FROM prescriptions GROUP BY status").fetchall()
    inventory_value = conn.execute("SELECT COALESCE(SUM(quantity * unit_price),0) AS value FROM inventory").fetchone()["value"]
    expired = conn.execute("SELECT COUNT(*) n FROM inventory WHERE expiry_date < ?", (date.today().isoformat(),)).fetchone()["n"]
    logs = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 15").fetchall()
    conn.close()
    return render_template("reports.html", status_rows=status_rows, inventory_value=inventory_value, expired=expired, logs=logs)

@app.route("/users", methods=["GET", "POST"])
@login_required
@roles_required("Administrator")
def users():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        username = f.get("username","").strip()
        password = f.get("password","")
        full_name = f.get("full_name","").strip()
        role = f.get("role","")
        if not username or len(password) < 8 or not full_name or role not in ROLES:
            flash("Provide all details and a password of at least 8 characters.", "error")
        else:
            try:
                conn.execute("INSERT INTO users(username,password_hash,full_name,role,created_at) VALUES(?,?,?,?,?)",
                             (username, generate_password_hash(password), full_name, role, datetime.now().isoformat(timespec="seconds")))
                conn.commit()
                audit("Create user", f"Created {username} with role {role}")
                flash("User account created.", "success")
                conn.close()
                return redirect(url_for("users"))
            except sqlite3.IntegrityError:
                flash("That username already exists.", "error")
    rows = conn.execute("SELECT id,username,full_name,role,created_at FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template("users.html", users=rows, roles=ROLES)

@app.route("/health")
def health():
    return jsonify(status="ok", application="Pharmacy Prescription Management System")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
