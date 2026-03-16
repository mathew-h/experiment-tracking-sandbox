from typing import Optional
from sqlalchemy.orm import Session
from .models import ScalarResults

class ScalarResultsService:
    def __init__(self, db: Session):
        self.db = db

    def create_scalar_result(self, result_id: int, scalar_data: dict) -> ScalarResults:
        """Create a new scalar result entry."""
        scalar_result = ScalarResults(result_id=result_id, **scalar_data)
        scalar_result.calculate_yields()  # Calculate derived values
        self.db.add(scalar_result)
        self.db.commit()
        self.db.refresh(scalar_result)
        return scalar_result

    def update_scalar_result(self, scalar_result: ScalarResults, update_data: dict) -> ScalarResults:
        """Update an existing scalar result entry."""
        for key, value in update_data.items():
            setattr(scalar_result, key, value)
        scalar_result.calculate_yields()  # Recalculate after updates
        self.db.commit()
        self.db.refresh(scalar_result)
        return scalar_result

    def get_scalar_result(self, result_id: int) -> Optional[ScalarResults]:
        """Get scalar result by result_id."""
        return self.db.query(ScalarResults).filter(ScalarResults.result_id == result_id).first()

    def delete_scalar_result(self, scalar_result: ScalarResults) -> None:
        """Delete a scalar result entry."""
        self.db.delete(scalar_result)
        self.db.commit() 