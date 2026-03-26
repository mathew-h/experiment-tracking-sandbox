# User Manual

The Experiment Tracking System is a web application for the Addis Energy geochemistry team to log and manage lab experiments, track samples and chemicals, upload bulk analytical data, and monitor reactor status. It runs on the lab PC and is accessible from any browser on the local network.

For detailed guides on specific features, see the sub-guides linked in the navigation below.

---

## Sub-Guides

- [Bulk Uploads Guide](BULK_UPLOADS.md) — All 12 upload types, templates, and field mappings
- [Dashboard Guide](DASHBOARD.md) — Reactor grid, status changes, and experiment cards

---

## Getting Started

1. Open a browser and navigate to `http://<lab-pc-hostname>:8000`
2. Log in with your `@addisenergy.com` Google or email account.
3. If you do not have an account, click **Register** and fill in your details. Your account must be approved by an administrator before you can log in. Contact the lab admin after registering.

---

## Main Pages

| Page | What it does |
|------|--------------|
| **Dashboard** (`/dashboard`) | Reactor grid showing all ONGOING experiments. Click a status badge to change an experiment's status (Ongoing → Completed or Cancelled). |
| **Experiments** (`/experiments`) | List all experiments. Click an experiment to open its detail view with Conditions, Results, and Analysis tabs. |
| **New Experiment** (`/experiments/new`) | 4-step guided form to create a new experiment: basic info, conditions, chemical additives, and confirmation. |
| **Bulk Uploads** (`/bulk-uploads`) | Accordion panel for uploading analytical data in bulk (solution chemistry, ICP-OES, XRD, pXRF, and more). See the [Bulk Uploads Guide](BULK_UPLOADS.md). |
| **Samples** (`/samples`) | Browse and manage geological sample inventory. |
| **Chemicals** (`/chemicals`) | Browse the reagent/compound inventory used in experiment conditions. |

---

## Experiment Lifecycle

Experiments move through a defined lifecycle from creation to completion:

1. **Create** — Use the New Experiment form (`/experiments/new`) to record the basic metadata: experiment ID, researcher, date, and the associated sample.
2. **Add Conditions** — Open the experiment's detail view and complete the Conditions tab: temperature, pH, reactor number, rock mass, water volume, and chemical additives.
3. **Add Results** — Upload analytical data via Bulk Uploads (preferred for multiple experiments at once) or enter results manually on the Results tab of the experiment detail view.
4. **Analyze** — Use the Analysis tab to attach external analyses (XRD, pXRF, SEM, elemental) or view Aeris XRD time-series data.
5. **Complete** — When the experiment is finished, change the status to **Completed** from the Dashboard or the experiment detail header. Cancelled experiments can be marked **Cancelled**.

---

## Common Tasks

| Task | How |
|------|-----|
| Create an experiment | Navigate to **New Experiment**, fill the 4-step form |
| Upload solution chemistry results | **Bulk Uploads** → Solution Chemistry → download template → fill in values → upload |
| Update experiment status | **Dashboard** → click the status badge on a reactor card → select new status |
| Check Water:Rock Ratio | Open an experiment → **Conditions** tab |
| Upload ICP data | **Bulk Uploads** → ICP-OES Data → upload the instrument CSV |
| View all results for an experiment | Open an experiment → **Results** tab |
| Attach an external analysis file | Open an experiment → **Analysis** tab → Add Analysis |
| Search for a sample | Navigate to **Samples**, use the search bar |
| Add a new user (admin only) | Run `python scripts/manage_users.py create <email> <password> <display_name>` on the lab PC, then `approve <request_id>` |
