# AetherCare · Smart Temperature Monitoring & Alert System

A hackathon-ready Flask application for simulated cold-chain monitoring. It records temperature readings, detects product-specific excursions, creates in-app alerts, and maintains incident timelines and audit history. It never automatically declares medicines or vaccines safe for use.

## Run locally

Requirements: Python 3.10 or later. The default setup uses a local SQLite database so the demo runs without a separate database server.

```powershell
cd temperature-monitor
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). At first launch, the app creates `instance/temperature_monitor.db` and seeds the demonstration users, locations, sensors, products, readings, and a sample incident. The database persists between launches.

### MySQL

The app uses Flask-SQLAlchemy and supports MySQL. Install MySQL 8+, execute `database.sql`, then configure the connection before starting Flask:

```powershell
$env:DATABASE_URL = "mysql+pymysql://username:password@localhost/temperature_monitor?charset=utf8mb4"
$env:SECRET_KEY = "replace-with-a-long-random-secret"
python app.py
```

The application creates missing tables at startup. `database.sql` is also provided as the explicit relational schema. Keep credentials and the production secret outside source control. For hosted HTTPS deployments, set `$env:COOKIE_SECURE = "1"`.

### Demo sign-in

| Role | Email | Password |
|---|---|---|
| Admin | `admin@demo.local` | `Admin123!` |
| Healthcare Staff | `staff@demo.local` | `Staff123!` |
| Auditor | `auditor@demo.local` | `Audit123!` |

The app stores Werkzeug password hashes. The displayed demo passwords are for local presentations only; replace or disable them before any shared deployment.

## Role access

| Capability | Admin | Healthcare Staff | Auditor |
|---|:---:|:---:|:---:|
| Monitor readings, alerts, incidents, and reports | ✓ | ✓ | ✓ |
| Add products and register sensors | ✓ | — | — |
| Add users and assign roles | ✓ | — | — |
| Create threshold versions | ✓ | — | — |
| Run the Simulation Lab | ✓ | ✓ | — |
| Acknowledge, note, escalate, assess incidents | ✓ | ✓ | — |
| Review audit log | ✓ | — | ✓ |

Permissions are checked by Flask routes and APIs. Forms and API writes use Flask-WTF CSRF protection. Passwords are hashed, and session cookies are HTTP-only and SameSite=Lax.

## Hackathon demo flow

1. Sign in as Healthcare Staff.
2. Open **Simulation Lab**, select a sensor, choose **High excursion** or **Sudden spike**, then start the simulation.
3. The browser sends generated sample temperatures to `POST /api/readings`. Flask stores each reading, compares it with the product's active threshold version, and writes incidents, timeline events, alerts, and audit events.
4. Open **Alert center** to acknowledge an alert, or **Incidents** to inspect its duration, add investigation notes, escalate, and record a human reviewer assessment.
5. Switch to the Auditor account to review the timeline, reports, and audit log in read-only mode.

Use **Low excursion**, **Prolonged excursion**, and the sensor connection controls to demonstrate other states. The speed slider changes the browser interval from one reading every 5 seconds up to five times faster. The prolonged notification threshold and unacknowledged escalation window can be configured with `PROLONGED_MINUTES` and `ESCALATION_MINUTES` environment variables; both default to 5 minutes.

## Pages and API

- `dashboard.html`: database-backed product, sensor, location, alert, and review summaries with a temperature trend chart.
- `monitoring.html`: live product cards and stored reading history.
- `simulation.html`: sensor selection, normal/high/low/spike/prolonged scenarios, connection controls, start/pause/stop, speed control, and reset.
- `products.html`, `sensors.html`, `locations.html`, and `team.html`: admin inventory, threshold version, device, and account workflows.
- `alerts.html`, `incidents.html`, and `incident_details.html`: acknowledgement, escalation, notes, reviewer assessment, and append-only timeline views.
- `reports.html`: date filters, CSV export, history, incident frequency/duration, acknowledgement time, sensor availability, and an auditor-visible audit log.
- JSON APIs under `/api/` serve page data and accept role-checked writes. `GET /api/reports.csv` exports a filtered reading history.

Temperature limits in the seed data are clearly marked demonstration values. Adding or changing a product's limits creates a new threshold version; readings and incidents keep the version that applied when they were recorded. Recovery only adds a recovery event. An incident remains pending until an authorized human records an assessment.

## Project structure

```text
temperature-monitor/
├── app.py
├── config.py
├── requirements.txt
├── database.sql
├── README.md
├── templates/
│   ├── login.html
│   ├── dashboard.html
│   ├── monitoring.html
│   ├── simulation.html
│   ├── products.html
│   ├── sensors.html
│   ├── alerts.html
│   ├── incidents.html
│   ├── incident_details.html
│   ├── reports.html
│   └── team.html
└── static/
    ├── css/style.css
    └── js/
        ├── app.js
        ├── login.js
        ├── dashboard.js
        ├── monitoring.js
        ├── simulation.js
        ├── alerts.js
        ├── incidents.js
        ├── incident-detail.js
        └── reports.js
```

Chart.js and Google Fonts load from public CDNs, so the charts and custom font need an internet connection. The rest of the app runs locally. In-app notifications are database-backed; email/SMS delivery requires a deployment-specific provider and is not simulated as delivered.

