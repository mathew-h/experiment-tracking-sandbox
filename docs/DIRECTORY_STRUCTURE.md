# Directory Structure (Target)

```
experiment_tracking/
├── CLAUDE.md                          ← root context file (navigation hub)
├── MODELS.md                          ← schema reference (read-only legacy)
├── README.md                          ← kept updated by Documentation Agent
├── .env                               ← never committed
├── .env.example                       ← committed, no real values
├── .gitignore
├── requirements.txt
│
├── .claude/
│   ├── CLAUDE.md                      ← root instructions
│   ├── skills/                        ← agent skill files (on-demand loading)
│   └── commands/                      ← slash commands (start-task, complete-task, new-milestone)
│
├── backend/
│   ├── CLAUDE.md                      ← backend-scoped context
│   ├── core/
│   │   ├── logging.py                 ← structlog config, correlation_id middleware
│   │   └── config.py                  ← pydantic-settings
│   ├── api/
│   │   ├── main.py                    ← FastAPI app entry point
│   │   ├── dependencies.py            ← DB session, auth dependencies
│   │   ├── routers/                   ← one file per domain
│   │   └── schemas/                   ← Pydantic v2 models, one file per domain
│   ├── auth/
│   │   └── firebase.py                ← token verification
│   └── services/
│       ├── calculations/              ← CALCULATION ENGINE
│       │   ├── __init__.py
│       │   ├── conditions.py          ← water_to_rock_ratio
│       │   ├── additives.py           ← mass_in_grams, moles_added, catalyst_ppm, etc.
│       │   ├── results.py             ← h2_micromoles, yield calculations
│       │   └── registry.py            ← trigger table: input field → affected derived fields
│       └── bulk_uploads/              ← existing parsers (do not modify logic)
│
├── database/
│   ├── CLAUDE.md                      ← database-scoped context
│   ├── models/                        ← SQLAlchemy models (locked, storage-only)
│   ├── connection.py                  ← engine + session factory
│   └── base.py                        ← declarative base
│
├── alembic/
│   ├── versions/                      ← never delete existing files
│   └── env.py
│
├── frontend/
│   ├── CLAUDE.md                      ← frontend-scoped context
│   ├── public/
│   │   └── logo.png                   ← user-provided brand logo
│   ├── src/
│   │   ├── assets/
│   │   │   └── brand.ts               ← hex codes, font tokens, spacing scale
│   │   ├── api/                       ← Axios client + domain API files
│   │   ├── auth/                      ← Firebase provider + ProtectedRoute
│   │   ├── components/
│   │   │   ├── ui/                    ← base component library
│   │   │   ├── ReactorDashboard/
│   │   │   ├── ExperimentDetail/
│   │   │   ├── SampleInput/
│   │   │   ├── ResultsViewer/
│   │   │   └── BulkUpload/
│   │   ├── layouts/                   ← AppLayout, AuthLayout
│   │   ├── pages/                     ← one file per route
│   │   ├── styles/
│   │   │   └── tokens.css             ← CSS custom properties
│   │   └── App.tsx
│   ├── dist/                          ← build output, served by FastAPI
│   ├── tailwind.config.ts             ← brand tokens wired into Tailwind
│   └── package.json
│
├── tests/
│   ├── api/
│   ├── models/
│   ├── services/
│   │   ├── calculations/              ← formula unit tests + registry tests
│   │   └── bulk_uploads/
│   └── fixtures/
│
├── docs/
│   ├── SCHEMA.md
│   ├── DOMAIN.md
│   ├── DESIGN.md                      ← UI vision + brand hex codes
│   ├── CALCULATIONS.md                ← all formulas, units, trigger rules
│   ├── LOGGING.md                     ← log levels, field schema, correlation_id usage
│   ├── STACK.md
│   ├── UPLOAD_FORMATS.md
│   ├── CODE_STANDARDS.md              ← Python + TypeScript standards
│   ├── GIT_WORKFLOW.md                ← branch rules, commit format, pre-merge checklist
│   ├── AGENT_SYSTEM.md                ← full agent reference (roles, plugins, workflow)
│   ├── LOCKED_COMPONENTS.md           ← what must not be modified
│   ├── ENVIRONMENT.md                 ← env vars, permitted/not-permitted operations
│   ├── DIRECTORY_STRUCTURE.md         ← this file
│   ├── milestones/                    ← one file per milestone + index
│   ├── working/                       ← plan.md (working memory)
│   ├── api/
│   ├── frontend/
│   ├── user_guide/
│   ├── developer/
│   ├── deployment/
│   ├── upload_templates/
│   └── sample_data/
│       ├── representative_sample.xlsx ← provided by user
│       └── FIELD_MAPPING.md
│
├── logs/
│   ├── app.log                        ← structured JSON (daily rotation, 30-day retention)
│   └── calculations.log               ← dedicated calculation event log
│
├── uploads/                           ← runtime upload staging directory
│
└── scripts/
    ├── install_services.bat
    ├── deploy.bat
    └── backup.bat
```
