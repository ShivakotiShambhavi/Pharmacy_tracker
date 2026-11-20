# Pharmacy Stock and Medicine Expiry Tracking System
SR University | School of Computer Science & AI

**Stack:** Python 3 + Flask + SQLite + Bootstrap 5 (CDN, needs internet for styling)

## How to run in VS Code
1. Install Python 3.9+ and open this folder in VS Code (File > Open Folder).
2. Open a terminal (Ctrl + `) and create a virtual environment:
   - Windows:  `python -m venv venv`  then  `venv\Scripts\activate`
   - Mac/Linux: `python3 -m venv venv`  then  `source venv/bin/activate`
3. Install dependencies:  `pip install -r requirements.txt`
4. Run:  `python app.py`   (or press F5 in VS Code)
5. Open http://127.0.0.1:5000 in your browser.

The database (`pharmacy.db`) and sample data are created automatically on first run.
To reset everything, stop the app and delete `pharmacy.db`.

## Demo logins
| Role               | Username   | Password   |
|--------------------|------------|------------|
| Admin              | admin      | admin123   |
| Pharmacist         | pharmacist | pharma123  |
| Inventory Manager  | manager    | manager123 |

## Screens (11, minimum required is 8)
1. Login  2. Dashboard  3. Medicine Catalog (+ add/edit form)  4. Batch details per medicine
5. Suppliers (+ form)  6. Purchases / Stock Inward (+ form)  7. Dispense / Stock Outward
8. Expired / Damaged stock write-off  9. Stock Ledger  10. Alerts  11. Reports  12. User Management (Admin)

## Mandatory reports (HTML view, Print, and CSV export)
- Current Stock Report
- Expired Medicine Report
- Near-Expiry Report (window set by `NEAR_EXPIRY_DAYS` in app.py, default 60 days)
- Supplier Purchase Report (filter by supplier and date)

## Role permissions
| Feature                              | Admin | Pharmacist | Inventory Manager |
|--------------------------------------|:-----:|:----------:|:-----------------:|
| Dashboard, alerts, ledger, view stock|  ✔   |     ✔     |        ✔         |
| Add/edit medicines, suppliers        |  ✔   |            |        ✔         |
| Record purchases (stock inward)      |  ✔   |            |        ✔         |
| Dispense medicine (stock outward)    |  ✔   |     ✔     |                   |
| Record expired/damaged stock         |  ✔   |     ✔     |        ✔         |
| Stock / Expired / Near-expiry reports|  ✔   |     ✔     |        ✔         |
| Supplier purchase report             |  ✔   |            |        ✔         |
| User management                      |  ✔   |            |                   |

## Key logic
- Medicines have many **batches** (batch no, expiry, quantity, supplier, cost).
- Every purchase, dispense and write-off is logged in the **stock ledger** (IN / OUT / EXPIRED / DAMAGED).
- Dispensing uses **FEFO** (first-expiry-first-out) and never issues expired batches.
- Alerts: low stock (usable quantity <= reorder level), near expiry, and expired stock.

## Project structure
```
app.py            Flask app: routes, database, business logic
requirements.txt  Dependencies
templates/        HTML pages (Jinja2)
static/style.css  Styling
pharmacy.db       SQLite database (auto-created)
```
