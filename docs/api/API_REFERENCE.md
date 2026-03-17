# API Reference

Base URL: `http://localhost:8000`
Auth: All endpoints require `Authorization: Bearer <firebase-id-token>` header.

## Experiments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments` | List experiments. Query: `skip`, `limit`, `status`, `researcher`, `sample_id` |
| GET | `/api/experiments/{experiment_id}` | Get single experiment by string ID |
| POST | `/api/experiments` | Create experiment |
| PATCH | `/api/experiments/{experiment_id}` | Update status, researcher, date, sample_id |
| DELETE | `/api/experiments/{experiment_id}` | Delete experiment (cascades all related data) |
| POST | `/api/experiments/{experiment_id}/notes` | Add a note |

## Conditions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conditions/{id}` | Get conditions by PK |
| GET | `/api/conditions/by-experiment/{experiment_id}` | Get conditions by experiment string ID |
| POST | `/api/conditions` | Create conditions (triggers `water_to_rock_ratio` calc) |
| PATCH | `/api/conditions/{id}` | Update conditions (recalculates derived fields) |

## Results

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/results/{experiment_id}` | List all result timepoints for an experiment |
| POST | `/api/results` | Create result entry |
| GET | `/api/results/scalar/{result_id}` | Get scalar result |
| POST | `/api/results/scalar` | Create scalar (triggers H2 + ammonium yield calc) |
| PATCH | `/api/results/scalar/{scalar_id}` | Update scalar (recalculates) |
| GET | `/api/results/icp/{result_id}` | Get ICP result |
| POST | `/api/results/icp` | Create ICP result |

## Samples

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/samples` | List samples. Query: `country`, `rock_classification`, `skip`, `limit` |
| GET | `/api/samples/{sample_id}` | Get sample |
| POST | `/api/samples` | Create sample |
| PATCH | `/api/samples/{sample_id}` | Update sample |

## Chemicals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chemicals/compounds` | List all compounds |
| GET | `/api/chemicals/compounds/{id}` | Get compound |
| POST | `/api/chemicals/compounds` | Create compound |
| GET | `/api/chemicals/additives/{conditions_id}` | List additives for a conditions record |
| POST | `/api/chemicals/additives/{conditions_id}` | Add additive (triggers full additive calc) |

## Analysis

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/analysis/xrd/{experiment_id}` | XRD phases for an experiment |
| GET | `/api/analysis/pxrf` | List pXRF readings. Query: `skip`, `limit` |
| GET | `/api/analysis/external/{experiment_id}` | External analyses for an experiment |

## Dashboard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/reactor-status` | All reactors with current ONGOING experiment |
| GET | `/api/dashboard/timeline/{experiment_id}` | All timepoints with scalar/ICP presence flags |

## Admin

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/recalculate/{model_type}/{id}` | Re-run calc engine. model_type: `conditions`, `scalar`, `additive` |

## Bulk Uploads

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/bulk-uploads/scalar-results` | Solution Chemistry Excel upload |
| POST | `/api/bulk-uploads/new-experiments` | New Experiments Excel upload |
| POST | `/api/bulk-uploads/pxrf` | pXRF data file upload |
| POST | `/api/bulk-uploads/aeris-xrd` | Aeris XRD file upload |

All bulk upload endpoints return:
```json
{"created": 5, "updated": 2, "skipped": 0, "errors": [], "message": "..."}
```

## Interactive Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
