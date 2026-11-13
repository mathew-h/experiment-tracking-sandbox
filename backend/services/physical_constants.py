"""Physical constants shared by the calculation engine and its services.

This module lives outside `backend.services.calculations` on purpose: that
package imports every formula module on import, and `conditions_calcs` imports
`elemental_composition_service`, so a constants module inside the package would
be a circular import for that service.

One definition each, so a formula module and a service cannot drift apart.
The SQL views repeat some of these values (H2 molar mass, Fe molar mass); those
copies are documented in .claude/rules/MODELS-views.md and guarded by tests.
"""
from __future__ import annotations

FE_MOLAR_MASS: float = 55.845    # g/mol, iron
FEO_MOLAR_MASS: float = 71.844   # g/mol, iron(II) oxide
H2_MOLAR_MASS: float = 2.01588   # g/mol, hydrogen gas
NH4_MOLAR_MASS: float = 18.04    # g/mol, ammonium ion

# Background ammonium assumed when a scalar row stores none (mM).
DEFAULT_BACKGROUND_AMMONIUM_MM: float = 0.2
