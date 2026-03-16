from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from database import ExperimentalConditions, Experiment

class ExperimentalConditionsService:
    
    @staticmethod
    def create_experimental_conditions(db: Session, experiment_id: str, conditions_data: Dict[str, Any]) -> Optional[ExperimentalConditions]:
        """
        Creates a new ExperimentalConditions record for a given experiment.

        Args:
            db: The database session.
            experiment_id: The string ID of the parent experiment.
            conditions_data: A dictionary containing the condition values.

        Returns:
            The created ExperimentalConditions object, or None if the experiment doesn't exist.
        """
        # Optional: Validate if the parent experiment exists
        experiment = db.query(Experiment).filter(Experiment.experiment_id == experiment_id).first()
        if not experiment:
            # Handle error: Experiment not found (log or raise exception)
            print(f"Error: Experiment with ID {experiment_id} not found.") 
            return None

        # Create the ExperimentalConditions instance
        # Ensure the foreign key 'experiment_id' (referencing Experiment.id) is correctly set
        # If your model expects the parent object's PK id:
        # conditions_data['experiment_id'] = experiment.id 
        # If your model expects the string experiment_id directly (less common for FKs but check your model):
        # conditions_data['experiment_id'] = experiment_id 
        # Let's assume the FK links to Experiment.id based on standard practice
        
        # Create the ExperimentalConditions instance, ensuring the foreign key is correctly set.
        # We use experiment_fk = experiment.id, assuming 'experiment_fk' is the name of the 
        # foreign key column in ExperimentalConditions linking to Experiment.id (PK).
        # The string experiment_id (e.g., "SERUM_MH_027") is also stored for convenience/denormalization.
        conditions = ExperimentalConditions(
            **conditions_data, 
            experiment_fk=experiment.id,  # Assign the integer PK of the experiment
            experiment_id=experiment.experiment_id # Keep the string ID as well if the model has it
        )
        
        # *** Call the method to calculate derived fields ***
        conditions.calculate_derived_conditions()
        
        # Add to the session (commit will happen in the calling context, e.g., Experiment service)
        db.add(conditions)
        db.flush() # Flush to assign ID if needed immediately
        db.refresh(conditions) # Refresh to get any DB-generated values
        
        return conditions

    @staticmethod
    def calculate_water_to_rock_ratio(rock_mass: float, water_volume: float) -> float:
        """
        Calculate the water-to-rock ratio based on rock mass and water volume.
        
        Args:
            rock_mass (float): Mass of rock in grams
            water_volume (float): Volume of water in milliliters
            
        Returns:
            float: Water-to-rock ratio (water_volume/rock_mass) if rock_mass > 0, otherwise 0.0
        """
        if rock_mass > 0:
            return water_volume / rock_mass
        return 0.0

    @staticmethod
    def update_experimental_conditions(db: Session, conditions_id: int, conditions_data: Dict[str, Any]) -> Optional[ExperimentalConditions]:
        """
        Updates an existing ExperimentalConditions record.

        Args:
            db: The database session.
            conditions_id: The ID of the experimental conditions to update.
            conditions_data: A dictionary containing the fields to update.

        Returns:
            The updated ExperimentalConditions object, or None if not found.
        """
        conditions = db.query(ExperimentalConditions).filter(ExperimentalConditions.id == conditions_id).first()
        if not conditions:
            # Handle error: Conditions not found
            print(f"Error: ExperimentalConditions with ID {conditions_id} not found.")
            return None

        # Update fields
        for key, value in conditions_data.items():
            if hasattr(conditions, key):
                setattr(conditions, key, value)

        # Recalculate derived fields on conditions
        conditions.calculate_derived_conditions()

        # Cascade recalculations to additives and scalar results for this experiment
        try:
            # Update additives derived values (elemental mass, catalyst %, ppm)
            for additive in list(getattr(conditions, 'chemical_additives', []) or []):
                additive.calculate_derived_values()

            # Update scalar results (ammonia yield using sampling/volume; hydrogen yield)
            experiment = getattr(conditions, 'experiment', None)
            if experiment is not None:
                for res in list(getattr(experiment, 'results', []) or []):
                    if getattr(res, 'scalar_data', None) is not None:
                        res.scalar_data.calculate_yields()
        except Exception:
            # Allow caller to manage transaction; we only ensure calculations attempted
            pass

        db.add(conditions) # Add to session, commit will be handled by caller
        db.flush()
        db.refresh(conditions)
        return conditions

    # You might also add update/get methods here later
    # @staticmethod
    # def update_experimental_conditions(db: Session, conditions_id: int, update_data: Dict[str, Any]) -> Optional[ExperimentalConditions]:
    #     ...

    # @staticmethod
    # def get_experimental_conditions(db: Session, experiment_id: str) -> Optional[ExperimentalConditions]:
    #     ...
