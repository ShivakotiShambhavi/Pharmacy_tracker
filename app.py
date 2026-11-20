"""
Pharmacy Stock and Medicine Expiry Tracking System
SR University | School of Computer Science & AI
Stack: Python (Flask) + SQLite + Bootstrap 5
"""
import csv
import io
import os
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, Response, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "pharmacy.db")
NEAR_EXPIRY_DAYS = 60          # medicines expiring within this many days are "near expiry"

ADMIN = "Admin"
PHARMACIST = "Pharmacist"
MANAGER = "Inventory Manager"
ROLES = [ADMIN, PHARMACIST, MANAGER]

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"


# ----------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    generic_name TEXT,
    category TEXT,
    unit TEXT DEFAULT 'Strips',
    reorder_level INTEGER NOT NULL DEFAULT 20,
    price REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_person TEXT,
    phone TEXT,
    email TEXT,
    address TEXT
);
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    supplier_id INTEGER REFERENCES suppliers(id),
    batch_no TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    unit_cost REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    invoice_no TEXT,
    purchase_date TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_cost REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    txn_type TEXT NOT NULL,            -- IN, OUT, EXPIRED, DAMAGED
    quantity INTEGER NOT NULL,
    txn_date TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    note TEXT
);
"""


def d(offset):
    """ISO date string relative to today (used for demo data)."""
    return (date.today() + timedelta(days=offset)).isoformat()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        users = [
            ("admin", "admin123", "System Administrator", ADMIN),
            ("pharmacist", "pharma123", "Priya Pharmacist", PHARMACIST),
            ("manager", "manager123", "Imran Inventory", MANAGER),
        ]
        for u, p, n, r in users:
            db.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
                       (u, generate_password_hash(p), n, r))

        suppliers = [
            ("MediLife Distributors", "Ravi Kumar", "9876500011", "sales@medilife.com", "Hyderabad"),
            ("HealthPlus Pharma", "Anita Rao", "9876500022", "orders@healthplus.com", "Warangal"),
            ("Sun Wholesale Drugs", "Suresh Babu", "9876500033", "info@sunwholesale.com", "Vijayawada"),
        ]
        db.executemany("INSERT INTO suppliers(name,contact_person,phone,email,address) VALUES(?,?,?,?,?)", suppliers)

        meds = [
            ("Paracetamol 500mg", "Paracetamol", "Analgesic", "Strips", 50, 15.0),
            ("Amoxicillin 250mg", "Amoxicillin", "Antibiotic", "Strips", 40, 62.0),
            ("Cetirizine 10mg", "Cetirizine", "Antihistamine", "Strips", 30, 28.0),
            ("Metformin 500mg", "Metformin", "Antidiabetic", "Strips", 40, 35.0),
            ("Omeprazole 20mg", "Omeprazole", "Antacid", "Strips", 25, 48.0),
            ("Cough Syrup 100ml", "Dextromethorphan", "Cough & Cold", "Bottles", 20, 85.0),
            ("Insulin Glargine", "Insulin", "Antidiabetic", "Vials", 10, 640.0),
        ]
        db.executemany("INSERT INTO medicines(name,generic_name,category,unit,reorder_level,price) VALUES(?,?,?,?,?,?)", meds)

        # (medicine_id, supplier_id, batch_no, expiry offset days, qty, cost)
        batches = [
            (1, 1, "PCM-2401", 300, 200, 10.0),
            (1, 1, "PCM-2310", 25, 40, 9.5),      # near expiry
            (2, 2, "AMX-2402", 180, 90, 45.0),
            (2, 2, "AMX-2305", -15, 30, 42.0),    # expired
            (3, 3, "CTZ-2403", 20, 15, 18.0),     # near expiry + low stock
            (4, 1, "MTF-2404", 400, 120, 22.0),
            (5, 2, "OMP-2312", 45, 60, 30.0),     # near expiry
            (6, 3, "CSY-2405", 220, 8, 55.0),     # low stock
            (7, 2, "INS-2406", 120, 25, 520.0),
            (3, 3, "CTZ-2301", -40, 20, 17.0),    # expired
        ]
        for med, sup, bno, off, qty, cost in batches:
            cur = db.execute("INSERT INTO batches(medicine_id,supplier_id,batch_no,expiry_date,quantity,unit_cost) VALUES(?,?,?,?,?,?)",
                             (med, sup, bno, d(off), qty, cost))
            bid = cur.lastrowid
            pdate = d(-60)
            db.execute("""INSERT INTO purchases(batch_id,medicine_id,supplier_id,invoice_no,purchase_date,quantity,unit_cost)
                          VALUES(?,?,?,?,?,?,?)""", (bid, med, sup, f"INV-{1000 + bid}", pdate, qty, cost))
            db.execute("""INSERT INTO transactions(batch_id,medicine_id,txn_type,quantity,txn_date,user_id,note)
                          VALUES(?,?,?,?,?,?,?)""", (bid, med, "IN", qty, pdate, 1, "Opening purchase"))
    db.commit()
    db.close()


# --------------------------------------------------------------------- auth
@app.before_request
def load_user():
    g.user = None
    if "user_id" in session:
        g.user = q("SELECT * FROM users WHERE id=?", (session["user_id"],), one=True)


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if g.user is None:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def roles_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if g.user is None:
                return redirect(url_for("login"))
            if g.user["role"] != ADMIN and g.user["role"] not in roles:
                flash("You do not have permission to open that page.", "danger")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return wrapper
    return deco


@app.context_processor
def inject_globals():
    return {"ROLES": ROLES, "ADMIN": ADMIN, "PHARMACIST": PHARMACIST, "MANAGER": MANAGER,
            "NEAR_DAYS": NEAR_EXPIRY_DAYS, "today": date.today().isoformat()}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = q("SELECT * FROM users WHERE username=?", (request.form["username"].strip(),), one=True)
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['full_name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------- helpers
def near_limit():
    return (date.today() + timedelta(days=NEAR_EXPIRY_DAYS)).isoformat()


def stock_summary():
    """One row per medicine with usable / expired quantities and a status."""
    rows = q("""
        SELECT m.*,
          COALESCE(SUM(CASE WHEN b.expiry_date >= :t THEN b.quantity END),0) AS usable_qty,
          COALESCE(SUM(CASE WHEN b.expiry_date <  :t THEN b.quantity END),0) AS expired_qty
        FROM medicines m LEFT JOIN batches b ON b.medicine_id = m.id
        GROUP BY m.id ORDER BY m.name""", {"t": date.today().isoformat()})
    out = []
    for r in rows:
        r = dict(r)
        if r["usable_qty"] == 0:
            r["status"] = "Out of Stock"
        elif r["usable_qty"] <= r["reorder_level"]:
            r["status"] = "Low Stock"
        else:
            r["status"] = "In Stock"
        r["value"] = r["usable_qty"] * r["price"]
        out.append(r)
    return out


def expired_batches():
    return q("""SELECT b.*, m.name AS medicine, m.unit, s.name AS supplier
                FROM batches b JOIN medicines m ON m.id=b.medicine_id
                LEFT JOIN suppliers s ON s.id=b.supplier_id
                WHERE b.expiry_date < ? AND b.quantity > 0 ORDER BY b.expiry_date""",
             (date.today().isoformat(),))


def near_expiry_batches():
    return q("""SELECT b.*, m.name AS medicine, m.unit, s.name AS supplier,
                  CAST(julianday(b.expiry_date) - julianday(?) AS INTEGER) AS days_left
                FROM batches b JOIN medicines m ON m.id=b.medicine_id
                LEFT JOIN suppliers s ON s.id=b.supplier_id
                WHERE b.expiry_date >= ? AND b.expiry_date <= ? AND b.quantity > 0
                ORDER BY b.expiry_date""",
             (date.today().isoformat(), date.today().isoformat(), near_limit()))


def log_txn(batch_id, med_id, ttype, qty, note=""):
    db = get_db()
    db.execute("""INSERT INTO transactions(batch_id,medicine_id,txn_type,quantity,txn_date,user_id,note)
                  VALUES(?,?,?,?,?,?,?)""",
               (batch_id, med_id, ttype, qty, date.today().isoformat(), g.user["id"], note))


def as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def render_report(title, columns, rows, **extra):
    """Render a report as HTML, or as CSV when ?export=csv is passed."""
    if request.args.get("export") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([label for _, label in columns])
        for r in rows:
            w.writerow([r[k] for k, _ in columns])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={title.replace(' ', '_')}.csv"})
    return render_template("report.html", title=title, columns=columns, rows=rows, **extra)


# --------------------------------------------------------------- dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    summary = stock_summary()
    stats = {
        "medicines": len(summary),
        "units": sum(r["usable_qty"] for r in summary),
        "low": sum(1 for r in summary if r["status"] in ("Low Stock", "Out of Stock")),
        "near": len(near_expiry_batches()),
        "expired": len(expired_batches()),
        "value": sum(r["value"] for r in summary),
    }
    recent = q("""SELECT t.*, m.name AS medicine, b.batch_no, u.full_name AS user
                  FROM transactions t JOIN medicines m ON m.id=t.medicine_id
                  JOIN batches b ON b.id=t.batch_id LEFT JOIN users u ON u.id=t.user_id
                  ORDER BY t.id DESC LIMIT 8""")
    return render_template("dashboard.html", stats=stats, recent=recent)


# --------------------------------------------------------------- medicines
@app.route("/medicines")
@login_required
def medicines():
    term = request.args.get("q", "").strip().lower()
    rows = [r for r in stock_summary()
            if not term or term in r["name"].lower() or term in (r["generic_name"] or "").lower()
            or term in (r["category"] or "").lower()]
    return render_template("medicines.html", rows=rows, term=term)


@app.route("/medicines/add", methods=["GET", "POST"])
@app.route("/medicines/<int:mid>/edit", methods=["GET", "POST"])
@roles_required(MANAGER)
def medicine_form(mid=None):
    med = q("SELECT * FROM medicines WHERE id=?", (mid,), one=True) if mid else None
    if request.method == "POST":
        f = request.form
        vals = (f["name"].strip(), f["generic_name"].strip(), f["category"].strip(), f["unit"].strip(),
                as_int(f["reorder_level"]), as_float(f["price"]))
        if not vals[0]:
            flash("Medicine name is required.", "danger")
        else:
            if med:
                execute("UPDATE medicines SET name=?,generic_name=?,category=?,unit=?,reorder_level=?,price=? WHERE id=?",
                        vals + (mid,))
                flash("Medicine updated.", "success")
            else:
                execute("INSERT INTO medicines(name,generic_name,category,unit,reorder_level,price) VALUES(?,?,?,?,?,?)", vals)
                flash("Medicine added to catalog.", "success")
            return redirect(url_for("medicines"))
    return render_template("medicine_form.html", med=med)


@app.route("/medicines/<int:mid>/delete", methods=["POST"])
@roles_required(MANAGER)
def medicine_delete(mid):
    if q("SELECT 1 FROM batches WHERE medicine_id=?", (mid,), one=True):
        flash("Cannot delete: this medicine already has batch/stock history.", "danger")
    else:
        execute("DELETE FROM medicines WHERE id=?", (mid,))
        flash("Medicine deleted.", "success")
    return redirect(url_for("medicines"))


@app.route("/medicines/<int:mid>/batches")
@login_required
def medicine_batches(mid):
    med = q("SELECT * FROM medicines WHERE id=?", (mid,), one=True)
    if not med:
        return redirect(url_for("medicines"))
    batches = q("""SELECT b.*, s.name AS supplier FROM batches b LEFT JOIN suppliers s ON s.id=b.supplier_id
                   WHERE b.medicine_id=? ORDER BY b.expiry_date""", (mid,))
    return render_template("batches.html", med=med, batches=batches)


# --------------------------------------------------------------- suppliers
@app.route("/suppliers")
@roles_required(MANAGER)
def suppliers():
    rows = q("""SELECT s.*, COUNT(p.id) AS purchases, COALESCE(SUM(p.quantity*p.unit_cost),0) AS total
                FROM suppliers s LEFT JOIN purchases p ON p.supplier_id=s.id GROUP BY s.id ORDER BY s.name""")
    return render_template("suppliers.html", rows=rows)


@app.route("/suppliers/add", methods=["GET", "POST"])
@app.route("/suppliers/<int:sid>/edit", methods=["GET", "POST"])
@roles_required(MANAGER)
def supplier_form(sid=None):
    sup = q("SELECT * FROM suppliers WHERE id=?", (sid,), one=True) if sid else None
    if request.method == "POST":
        f = request.form
        vals = (f["name"].strip(), f["contact_person"].strip(), f["phone"].strip(), f["email"].strip(), f["address"].strip())
        if not vals[0]:
            flash("Supplier name is required.", "danger")
        else:
            if sup:
                execute("UPDATE suppliers SET name=?,contact_person=?,phone=?,email=?,address=? WHERE id=?", vals + (sid,))
                flash("Supplier updated.", "success")
            else:
                execute("INSERT INTO suppliers(name,contact_person,phone,email,address) VALUES(?,?,?,?,?)", vals)
                flash("Supplier added.", "success")
            return redirect(url_for("suppliers"))
    return render_template("supplier_form.html", sup=sup)


@app.route("/suppliers/<int:sid>/delete", methods=["POST"])
@roles_required(MANAGER)
def supplier_delete(sid):
    if q("SELECT 1 FROM purchases WHERE supplier_id=?", (sid,), one=True):
        flash("Cannot delete: supplier has purchase history.", "danger")
    else:
        execute("DELETE FROM suppliers WHERE id=?", (sid,))
        flash("Supplier deleted.", "success")
    return redirect(url_for("suppliers"))


# --------------------------------------------------------------- purchases (stock inward)
@app.route("/purchases")
@roles_required(MANAGER)
def purchases():
    rows = q("""SELECT p.*, m.name AS medicine, s.name AS supplier, b.batch_no, b.expiry_date
                FROM purchases p JOIN medicines m ON m.id=p.medicine_id
                JOIN suppliers s ON s.id=p.supplier_id JOIN batches b ON b.id=p.batch_id
                ORDER BY p.purchase_date DESC, p.id DESC""")
    return render_template("purchases.html", rows=rows)


@app.route("/purchases/new", methods=["GET", "POST"])
@roles_required(MANAGER)
def purchase_new():
    meds = q("SELECT id,name FROM medicines ORDER BY name")
    sups = q("SELECT id,name FROM suppliers ORDER BY name")
    if request.method == "POST":
        f = request.form
        med_id, sup_id = as_int(f["medicine_id"]), as_int(f["supplier_id"])
        qty, cost = as_int(f["quantity"]), as_float(f["unit_cost"])
        batch_no, expiry = f["batch_no"].strip(), f["expiry_date"]
        if not (med_id and sup_id and batch_no and expiry) or qty <= 0:
            flash("Please fill all fields with valid values (quantity must be > 0).", "danger")
        elif expiry <= date.today().isoformat():
            flash("Expiry date must be in the future.", "danger")
        else:
            cur = execute("""INSERT INTO batches(medicine_id,supplier_id,batch_no,expiry_date,quantity,unit_cost)
                             VALUES(?,?,?,?,?,?)""", (med_id, sup_id, batch_no, expiry, qty, cost))
            bid = cur.lastrowid
            execute("""INSERT INTO purchases(batch_id,medicine_id,supplier_id,invoice_no,purchase_date,quantity,unit_cost)
                       VALUES(?,?,?,?,?,?,?)""",
                    (bid, med_id, sup_id, f["invoice_no"].strip(), f["purchase_date"] or date.today().isoformat(), qty, cost))
            log_txn(bid, med_id, "IN", qty, f"Purchase {f['invoice_no'].strip()}")
            get_db().commit()
            flash("Purchase recorded and stock updated.", "success")
            return redirect(url_for("purchases"))
    return render_template("purchase_form.html", meds=meds, sups=sups)


# --------------------------------------------------------------- stock outward (dispense)
@app.route("/stock/out", methods=["GET", "POST"])
@roles_required(PHARMACIST)
def stock_out():
    summary = [r for r in stock_summary() if r["usable_qty"] > 0]
    if request.method == "POST":
        med_id, qty = as_int(request.form["medicine_id"]), as_int(request.form["quantity"])
        note = request.form["note"].strip()
        batches = q("""SELECT * FROM batches WHERE medicine_id=? AND quantity>0 AND expiry_date>=?
                       ORDER BY expiry_date""", (med_id, date.today().isoformat()))
        available = sum(b["quantity"] for b in batches)
        if qty <= 0:
            flash("Quantity must be greater than zero.", "danger")
        elif qty > available:
            flash(f"Insufficient stock. Only {available} unexpired units available.", "danger")
        else:
            remaining = qty
            for b in batches:                       # FEFO: First-Expiry-First-Out
                take = min(b["quantity"], remaining)
                get_db().execute("UPDATE batches SET quantity=quantity-? WHERE id=?", (take, b["id"]))
                log_txn(b["id"], med_id, "OUT", take, note or "Dispensed")
                remaining -= take
                if remaining == 0:
                    break
            get_db().commit()
            flash(f"Dispensed {qty} unit(s) using earliest-expiry batches first.", "success")
            return redirect(url_for("stock_out"))
    return render_template("stock_out.html", meds=summary)


# --------------------------------------------------------------- expired / damaged stock
@app.route("/stock/writeoff", methods=["GET", "POST"])
@roles_required(PHARMACIST, MANAGER)
def writeoff():
    if request.method == "POST":
        bid, reason = as_int(request.form["batch_id"]), request.form["reason"]
        batch = q("SELECT * FROM batches WHERE id=?", (bid,), one=True)
        qty = as_int(request.form.get("quantity")) or (batch["quantity"] if batch else 0)
        if reason not in ("EXPIRED", "DAMAGED") or not batch:
            flash("Invalid request.", "danger")
        elif qty <= 0 or qty > batch["quantity"]:
            flash(f"Quantity must be between 1 and {batch['quantity']}.", "danger")
        else:
            execute("UPDATE batches SET quantity=quantity-? WHERE id=?", (qty, bid))
            log_txn(bid, batch["medicine_id"], reason, qty, request.form.get("note", "").strip())
            get_db().commit()
            flash(f"{qty} unit(s) recorded as {reason.lower()} stock.", "success")
        return redirect(url_for("writeoff"))
    batches = q("""SELECT b.*, m.name AS medicine FROM batches b JOIN medicines m ON m.id=b.medicine_id
                   WHERE b.quantity>0 ORDER BY m.name, b.expiry_date""")
    history = q("""SELECT t.*, m.name AS medicine, b.batch_no, u.full_name AS user
                   FROM transactions t JOIN medicines m ON m.id=t.medicine_id JOIN batches b ON b.id=t.batch_id
                   LEFT JOIN users u ON u.id=t.user_id WHERE t.txn_type IN ('EXPIRED','DAMAGED')
                   ORDER BY t.id DESC LIMIT 15""")
    return render_template("writeoff.html", batches=batches, expired=expired_batches(), history=history)


# --------------------------------------------------------------- transaction history
@app.route("/transactions")
@login_required
def transactions():
    ttype = request.args.get("type", "")
    sql = """SELECT t.*, m.name AS medicine, b.batch_no, u.full_name AS user
             FROM transactions t JOIN medicines m ON m.id=t.medicine_id JOIN batches b ON b.id=t.batch_id
             LEFT JOIN users u ON u.id=t.user_id"""
    args = ()
    if ttype:
        sql += " WHERE t.txn_type=?"
        args = (ttype,)
    rows = q(sql + " ORDER BY t.id DESC LIMIT 300", args)
    return render_template("transactions.html", rows=rows, ttype=ttype)


# --------------------------------------------------------------- alerts
@app.route("/alerts")
@login_required
def alerts():
    low = [r for r in stock_summary() if r["status"] in ("Low Stock", "Out of Stock")]
    return render_template("alerts.html", low=low, near=near_expiry_batches(), expired=expired_batches())


# --------------------------------------------------------------- reports
@app.route("/reports")
@login_required
def reports():
    return render_template("reports_index.html")


@app.route("/reports/current-stock")
@login_required
def report_current():
    rows = stock_summary()
    for r in rows:
        r["_cls"] = {"Out of Stock": "table-danger", "Low Stock": "table-warning"}.get(r["status"], "")
        r["value"] = round(r["value"], 2)
    cols = [("name", "Medicine"), ("category", "Category"), ("unit", "Unit"), ("usable_qty", "Usable Qty"),
            ("expired_qty", "Expired Qty"), ("reorder_level", "Reorder Level"), ("price", "Price"),
            ("value", "Stock Value"), ("status", "Status")]
    return render_report("Current Stock Report", cols, rows)


@app.route("/reports/expired")
@login_required
def report_expired():
    rows = [dict(r, _cls="table-danger", loss=round(r["quantity"] * r["unit_cost"], 2)) for r in expired_batches()]
    cols = [("medicine", "Medicine"), ("batch_no", "Batch No"), ("expiry_date", "Expired On"),
            ("quantity", "Qty Remaining"), ("unit_cost", "Unit Cost"), ("loss", "Potential Loss"), ("supplier", "Supplier")]
    return render_report("Expired Medicine Report", cols, rows)


@app.route("/reports/near-expiry")
@login_required
def report_near():
    rows = [dict(r, _cls="table-danger" if r["days_left"] <= 30 else "table-warning") for r in near_expiry_batches()]
    cols = [("medicine", "Medicine"), ("batch_no", "Batch No"), ("expiry_date", "Expiry Date"),
            ("days_left", "Days Left"), ("quantity", "Quantity"), ("supplier", "Supplier")]
    return render_report(f"Near-Expiry Report (next {NEAR_EXPIRY_DAYS} days)", cols, rows)


@app.route("/reports/supplier-purchases")
@roles_required(MANAGER)
def report_supplier():
    sid = request.args.get("supplier_id", "")
    start, end = request.args.get("start", ""), request.args.get("end", "")
    sql = """SELECT p.purchase_date, s.name AS supplier, p.invoice_no, m.name AS medicine, b.batch_no,
                    p.quantity, p.unit_cost, ROUND(p.quantity*p.unit_cost,2) AS total
             FROM purchases p JOIN suppliers s ON s.id=p.supplier_id JOIN medicines m ON m.id=p.medicine_id
             JOIN batches b ON b.id=p.batch_id WHERE 1=1"""
    args = []
    if sid:
        sql += " AND p.supplier_id=?"; args.append(sid)
    if start:
        sql += " AND p.purchase_date>=?"; args.append(start)
    if end:
        sql += " AND p.purchase_date<=?"; args.append(end)
    rows = [dict(r) for r in q(sql + " ORDER BY p.purchase_date DESC", args)]
    cols = [("purchase_date", "Date"), ("supplier", "Supplier"), ("invoice_no", "Invoice"), ("medicine", "Medicine"),
            ("batch_no", "Batch"), ("quantity", "Qty"), ("unit_cost", "Unit Cost"), ("total", "Total")]
    grand = round(sum(r["total"] for r in rows), 2)
    return render_report("Supplier Purchase Report", cols, rows, supplier_filter=True,
                         suppliers=q("SELECT id,name FROM suppliers ORDER BY name"),
                         sel=dict(supplier_id=sid, start=start, end=end), footer=f"Grand total: ₹ {grand}")


# --------------------------------------------------------------- user management (Admin)
@app.route("/users")
@roles_required()
def users():
    return render_template("users.html", rows=q("SELECT * FROM users ORDER BY role, username"))


@app.route("/users/add", methods=["GET", "POST"])
@roles_required()
def user_add():
    if request.method == "POST":
        f = request.form
        if f["role"] not in ROLES or not f["username"].strip() or len(f["password"]) < 6:
            flash("Fill all fields; password must be at least 6 characters.", "danger")
        elif q("SELECT 1 FROM users WHERE username=?", (f["username"].strip(),), one=True):
            flash("Username already exists.", "danger")
        else:
            execute("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
                    (f["username"].strip(), generate_password_hash(f["password"]), f["full_name"].strip(), f["role"]))
            flash("User created.", "success")
            return redirect(url_for("users"))
    return render_template("user_form.html")


@app.route("/users/<int:uid>/delete", methods=["POST"])
@roles_required()
def user_delete(uid):
    if uid == g.user["id"]:
        flash("You cannot delete your own account.", "danger")
    elif q("SELECT 1 FROM transactions WHERE user_id=?", (uid,), one=True):
        flash("User has transaction history and cannot be deleted.", "danger")
    else:
        execute("DELETE FROM users WHERE id=?", (uid,))
        flash("User deleted.", "success")
    return redirect(url_for("users"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
