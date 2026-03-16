# Code Standards

## Python (Backend)
- Python 3.11+, type hints on all signatures, no `Any` without justification
- FastAPI for all endpoints; SQLAlchemy 2.x style (`select()`, `Session.execute()`); Pydantic v2
- `structlog` for all logging — never `print()` or stdlib `logging.basicConfig()`
- `pydantic-settings` for all config — never `os.environ.get()` with hardcoded fallbacks
- Black (line length 88), isort; `HTTPException` with specific status codes; `Depends(get_db)` for sessions
- No business logic inside SQLAlchemy model files — models are storage definitions only

```python
# Correct endpoint pattern
@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Retrieve a single experiment by its string identifier."""
    experiment = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentResponse.model_validate(experiment)

# Correct write endpoint pattern (triggers calculation engine)
@router.post("/conditions", response_model=ConditionsResponse, status_code=201)
async def create_conditions(
    payload: ConditionsCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    """Create experimental conditions and compute all derived fields."""
    conditions = ExperimentalConditions(**payload.model_dump())
    db.add(conditions)
    db.flush()
    affected = registry.get_affected_fields("ExperimentalConditions", set(payload.model_fields_set))
    calculation_service.run(db, conditions, affected)
    db.commit()
    db.refresh(conditions)
    return ConditionsResponse.model_validate(conditions)
```

## TypeScript / React (Frontend)
- React 18 + TypeScript strict mode; functional components only; props interfaces on every component
- React Query for all server state — no `useEffect` + `useState` for data fetching
- React Router v6 for navigation; Tailwind utility classes only — no inline styles
- Never hardcode hex values in components — always reference brand tokens from `brand.ts`
- ESLint + Prettier zero warnings; no `console.log` in committed code

```typescript
interface ReactorCardProps {
  reactorId: string;
  experimentId: string | null;
  status: ExperimentStatus | null;
  onSelect: (reactorId: string) => void;
}

export function ReactorCard({ reactorId, experimentId, status, onSelect }: ReactorCardProps): JSX.Element {
  return (
    <div
      className="rounded-lg border border-surface-200 p-4 cursor-pointer hover:border-primary"
      onClick={() => onSelect(reactorId)}
    >
      {/* never: style={{ color: '#2563eb' }} — always use token classes */}
    </div>
  );
}
```

## Testing Standards
- Backend: pytest, pytest-asyncio, httpx `TestClient`; frontend: Vitest, React Testing Library, MSW
- Test file location mirrors source structure
- Every test is independent — no shared mutable state
- Fixtures for DB setup/teardown — never use production DB in tests
- Calculation engine tests: every formula must have a test with known numeric inputs/outputs taken from existing Streamlit-computed values
