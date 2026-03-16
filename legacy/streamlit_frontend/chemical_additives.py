import streamlit as st
from database import SessionLocal
from database.models import Compound
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
import logging
import pandas as pd

logger = logging.getLogger(__name__)

def get_all_compounds(db_session: Session) -> List[Compound]:
    """Retrieve all compounds from the database"""
    try:
        return db_session.query(Compound).order_by(Compound.name).all()
    except Exception as e:
        # If table doesn't exist yet, return empty list
        if "no such table" in str(e).lower():
            logger.info("Compounds table doesn't exist yet, returning empty list")
            return []
        logger.error(f"Error retrieving compounds: {e}")
        st.error(f"Error loading compounds: {e}")
        return []

def render_chemical_management():
    """
    Render the Compound Management interface - the single source of truth for all chemicals
    """
    st.title("🧪 Chemical Management")
    st.markdown("**Single source of truth for all chemicals in the system**")
    
    # Get database session
    db_session = SessionLocal()
    
    try:
        # Load compounds for display
        compounds = get_all_compounds(db_session)
        
        # Display compounds table
        st.subheader("📋 Compound Library")
        
        if compounds:
            # Create DataFrame with selected columns
            df_data = []
            for c in compounds:
                df_data.append({
                    'Name': c.name,
                    'Formula': c.formula if c.formula else '',
                    'Molecular Weight (g/mol)': c.molecular_weight if c.molecular_weight else None,
                    'Density (g/cm³)': c.density if c.density else None,
                })
            
            df = pd.DataFrame(df_data)
            
            # Quick search filter with dropdown
            # Create search options combining name and formula
            search_options = ["All Compounds"] + [
                f"{row['Name']}{' (' + row['Formula'] + ')' if row['Formula'] else ''}"
                for _, row in df.iterrows()
            ]
            
            selected_compound = st.selectbox(
                "🔍 Quick Search",
                options=search_options,
                help="Select a compound to view details",
                key="compound_search"
            )
            
            # Filter dataframe based on selection
            if selected_compound and selected_compound != "All Compounds":
                # Extract compound name from selection (before the parentheses if present)
                compound_name = selected_compound.split(' (')[0] if ' (' in selected_compound else selected_compound
                filtered_df = df[df['Name'] == compound_name]
            else:
                filtered_df = df
            
            # Display the dataframe with search functionality
            st.dataframe(
                filtered_df,
                use_container_width=True,
                hide_index=True,
                height=400
            )
            
            st.markdown(f"**Showing {len(filtered_df)} of {len(df)} compounds**")
        else:
            st.info("No compounds in the library yet. Add your first compound below.")
        
        st.markdown("---")
           
        # Add New Compound Form
        st.subheader("➕ Add New Compound")
        
        with st.form("add_compound_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                compound_name = st.text_input(
                    "Compound Name *",
                    placeholder="e.g., Potassium Chloride",
                    help="Required: The common name of the compound"
                )
                
                formula = st.text_input(
                    "Chemical Formula",
                    placeholder="e.g., KCl",
                    help="Optional: Chemical formula"
                )
                
                cas_number = st.text_input(
                    "CAS Number",
                    placeholder="e.g., 7447-40-7",
                    help="Optional: CAS registry number"
                )
                
                molecular_weight = st.number_input(
                    "Molecular Weight (g/mol)",
                    min_value=0.0,
                    value=None,
                    step=0.01,
                    format="%.2f",
                    help="Optional: Molecular weight in g/mol"
                )
                
                density = st.number_input(
                    "Density (g/cm³)",
                    min_value=0.0,
                    value=None,
                    step=0.001,
                    format="%.3f",
                    help="Optional: Density for solids (g/cm³) or liquids (g/mL)"
                )
            
            with col2:
                melting_point = st.number_input(
                    "Melting Point (°C)",
                    value=None,
                    step=0.1,
                    format="%.1f",
                    help="Optional: Melting point in Celsius"
                )
                
                boiling_point = st.number_input(
                    "Boiling Point (°C)",
                    value=None,
                    step=0.1,
                    format="%.1f",
                    help="Optional: Boiling point in Celsius"
                )
                
                solubility = st.text_input(
                    "Solubility",
                    placeholder="e.g., Soluble in water",
                    help="Optional: Solubility description"
                )
                
                hazard_class = st.text_input(
                    "Hazard Class",
                    placeholder="e.g., Non-hazardous",
                    help="Optional: Safety/hazard information"
                )
            
            # Supplier Information
            st.markdown("**Supplier Information**")
            col3, col4 = st.columns(2)
            
            with col3:
                supplier = st.text_input(
                    "Supplier",
                    placeholder="e.g., Sigma-Aldrich",
                    help="Optional: Supplier name"
                )
                
                catalog_number = st.text_input(
                    "Catalog Number",
                    placeholder="e.g., P5405",
                    help="Optional: Supplier catalog number"
                )
            
            with col4:
                notes = st.text_area(
                    "Notes",
                    placeholder="Additional notes about the compound...",
                    help="Optional: Additional information"
                )
            
            # Submit button
            submitted = st.form_submit_button("💾 Add Compound", type="primary", use_container_width=True)
            
            if submitted:

                # Create a new database session for the form submission
                form_session = SessionLocal()

                try:
                    # Enhanced validation with specific error messages
                    validation_errors = []

                    if not compound_name or not compound_name.strip():
                        validation_errors.append("❌ **Compound name is required** - Please enter a compound name")
                    elif len(compound_name.strip()) < 2:
                        validation_errors.append("❌ **Compound name too short** - Please enter at least 2 characters")
                    elif len(compound_name.strip()) > 100:
                        validation_errors.append("❌ **Compound name too long** - Please enter a name with 100 characters or less")

                    # Validate CAS number format if provided
                    if cas_number and cas_number.strip():
                        cas_clean = cas_number.strip()
                        if not cas_clean.replace('-', '').replace('.', '').isdigit():
                            validation_errors.append("❌ **Invalid CAS number format** - CAS numbers should contain only numbers, hyphens, and dots")
                        elif len(cas_clean) < 5 or len(cas_clean) > 20:
                            validation_errors.append("❌ **Invalid CAS number length** - CAS numbers should be between 5-20 characters")

                    # Validate molecular weight if provided
                    if molecular_weight is not None and molecular_weight <= 0:
                        validation_errors.append("❌ **Invalid molecular weight** - Molecular weight must be greater than 0")
                    elif molecular_weight is not None and molecular_weight > 10000:
                        validation_errors.append("❌ **Molecular weight too high** - Please check the value (max: 10,000 g/mol)")

                    # Validate density if provided
                    if density is not None and density <= 0:
                        validation_errors.append("❌ **Invalid density** - Density must be greater than 0")
                    elif density is not None and density > 50:
                        validation_errors.append("❌ **Density too high** - Please check the value (max: 50 g/cm³)")

                    # Display validation errors
                    if validation_errors:
                        st.error("**Please fix the following issues:**")
                        for error in validation_errors:
                            st.error(error)
                    else:
                        # Check for duplicate names
                        existing_compound = form_session.query(Compound).filter(
                            Compound.name.ilike(compound_name.strip())
                        ).first()
                    
                        if existing_compound:
                            st.error(f"❌ A compound with the name '{compound_name}' already exists!")
                        else:
                            # Initialize to avoid UnboundLocalError when CAS not provided
                            existing_cas = None
                            # Check for duplicate CAS numbers if provided
                            if cas_number and cas_number.strip():
                                existing_cas = form_session.query(Compound).filter(
                                    Compound.cas_number == cas_number.strip()
                                ).first()
                            
                            if existing_cas:
                                st.error(f"❌ A compound with CAS number '{cas_number}' already exists!")
                            
                            # If we reach here, no duplicates were found
                            try:
                                # Create new compound
                                new_compound = Compound(
                                        name=compound_name.strip(),
                                        formula=formula.strip() if formula else None,
                                        cas_number=cas_number.strip() if cas_number else None,
                                        molecular_weight=molecular_weight if molecular_weight else None,
                                        density=density if density else None,
                                        melting_point=melting_point if melting_point else None,
                                        boiling_point=boiling_point if boiling_point else None,
                                        solubility=solubility.strip() if solubility else None,
                                        hazard_class=hazard_class.strip() if hazard_class else None,
                                        supplier=supplier.strip() if supplier else None,
                                        catalog_number=catalog_number.strip() if catalog_number else None,
                                        notes=notes.strip() if notes else None
                                    )
                                form_session.add(new_compound)
                                form_session.flush()
                                form_session.commit()
                                # Verify the compound was actually saved
                                saved_compound = form_session.query(Compound).filter(
                                    Compound.name == compound_name.strip()
                                ).first()

                                if saved_compound:
                                    st.success(f"✅ Successfully added compound: {compound_name}")
                                    st.rerun()
                                else:
                                    st.error("❌ **CRITICAL ERROR**: Compound was not found in database after save!")
                                    st.error("This indicates a serious database issue.")

                            except Exception as e:
                                st.error(f"❌ **COMPOUND CREATION FAILED**: {str(e)}")
                                st.error(f"Error type: {type(e).__name__}")
                                raise  # Re-raise to trigger the outer exception handler

                except Exception as e:
                    form_session.rollback()
                    logger.error(f"Error adding compound: {e}")

                    # Provide specific error messages based on exception type
                    if "UNIQUE constraint failed" in str(e):
                        if "name" in str(e).lower():
                            st.error("❌ **Duplicate Name Error**: A compound with this name already exists. Please choose a different name.")
                        elif "cas_number" in str(e).lower():
                            st.error("❌ **Duplicate CAS Number Error**: A compound with this CAS number already exists. Please check the CAS number or leave it blank.")
                        else:
                            st.error("❌ **Duplicate Data Error**: Some of the provided information already exists in the database. Please check for duplicates.")
                    elif "NOT NULL constraint failed" in str(e):
                        st.error("❌ **Required Field Error**: One or more required fields are missing. Please fill in all mandatory fields.")
                    elif "FOREIGN KEY constraint failed" in str(e):
                        st.error("❌ **Database Relationship Error**: There's an issue with database relationships. Please try again or contact support.")
                    elif "database is locked" in str(e).lower():
                        st.error("❌ **Database Locked Error**: The database is currently in use. Please wait a moment and try again.")
                    elif "disk full" in str(e).lower() or "no space left" in str(e).lower():
                        st.error("❌ **Storage Error**: Insufficient disk space. Please free up space and try again.")
                    else:
                        st.error(f"❌ **Unexpected Error**: Failed to save compound. Error details: {str(e)}")

                    # Show troubleshooting tips
                    with st.expander("Troubleshooting Tips", expanded=False):
                        st.markdown("""
                        - Check that all required fields are filled
                        - Ensure compound names and CAS numbers are unique
                        - Try refreshing the page and attempting again
                        - Contact support if the problem persists
                        """)

                finally:
                    form_session.close()
    
    except Exception as e:
        logger.error(f"Error in compound management: {e}")
        
        # Provide specific error messages for loading failures
        if "database is locked" in str(e).lower():
            st.error("❌ **Database Locked Error**: The database is currently in use. Please wait a moment and try again.")
        elif "no such table" in str(e).lower():
            st.error("❌ **Database Schema Error**: The compound tables don't exist. Please run database migrations.")
        elif "permission denied" in str(e).lower():
            st.error("❌ **Permission Error**: You don't have permission to access compound management. Contact your administrator.")
        elif "connection" in str(e).lower():
            st.error("❌ **Connection Error**: Unable to connect to the database. Please check your connection and try again.")
        else:
            st.error(f"❌ **Loading Error**: Failed to load compound management. Error details: {str(e)}")
        
        # Show troubleshooting tips for loading errors
        with st.expander("🔧 Troubleshooting Tips", expanded=False):
            st.markdown("""
            **If the page fails to load:**
            - Check your internet connection
            - Ensure the database is accessible
            - Try refreshing the page
            - Contact support if the problem persists
            """)
    finally:
        db_session.close()

# Backward compatibility for existing imports
def render_compound_management():
    return render_chemical_management()

def render_edit_compound_form(compound_id: int):
    """Render form for editing an existing compound"""
    db_session = SessionLocal()
    
    try:
        compound = db_session.query(Compound).filter(Compound.id == compound_id).first()
        
        if not compound:
            st.error("Compound not found!")
            return
        
        st.subheader(f"✏️ Edit Compound: {compound.name}")
        
        with st.form("edit_compound_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input("Name", value=compound.name)
                formula = st.text_input("Formula", value=compound.formula or "")
                cas_number = st.text_input("CAS Number", value=compound.cas_number or "")
                molecular_weight = st.number_input(
                    "Molecular Weight (g/mol)",
                    value=compound.molecular_weight or 0.0,
                    step=0.01,
                    format="%.2f"
                )
                density = st.number_input(
                    "Density (g/cm³)",
                    value=compound.density or 0.0,
                    step=0.001,
                    format="%.3f"
                )
            
            with col2:
                melting_point = st.number_input(
                    "Melting Point (°C)",
                    value=compound.melting_point or 0.0,
                    step=0.1,
                    format="%.1f"
                )
                boiling_point = st.number_input(
                    "Boiling Point (°C)",
                    value=compound.boiling_point or 0.0,
                    step=0.1,
                    format="%.1f"
                )
                supplier = st.text_input("Supplier", value=compound.supplier or "")
                catalog_number = st.text_input("Catalog Number", value=compound.catalog_number or "")
                notes = st.text_area("Notes", value=compound.notes or "")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                if st.form_submit_button("💾 Save Changes", type="primary"):
                    # Enhanced validation for edit form
                    validation_errors = []
                    
                    if not name or not name.strip():
                        validation_errors.append("❌ **Compound name is required** - Please enter a compound name")
                    elif len(name.strip()) < 2:
                        validation_errors.append("❌ **Compound name too short** - Please enter at least 2 characters")
                    elif len(name.strip()) > 100:
                        validation_errors.append("❌ **Compound name too long** - Please enter a name with 100 characters or less")
                    
                    # Validate CAS number format if provided
                    if cas_number and cas_number.strip():
                        cas_clean = cas_number.strip()
                        if not cas_clean.replace('-', '').replace('.', '').isdigit():
                            validation_errors.append("❌ **Invalid CAS number format** - CAS numbers should contain only numbers, hyphens, and dots")
                        elif len(cas_clean) < 5 or len(cas_clean) > 20:
                            validation_errors.append("❌ **Invalid CAS number length** - CAS numbers should be between 5-20 characters")
                    
                    # Validate molecular weight if provided
                    if molecular_weight is not None and molecular_weight <= 0:
                        validation_errors.append("❌ **Invalid molecular weight** - Molecular weight must be greater than 0")
                    elif molecular_weight is not None and molecular_weight > 10000:
                        validation_errors.append("❌ **Molecular weight too high** - Please check the value (max: 10,000 g/mol)")
                    
                    # Validate density if provided
                    if density is not None and density <= 0:
                        validation_errors.append("❌ **Invalid density** - Density must be greater than 0")
                    elif density is not None and density > 50:
                        validation_errors.append("❌ **Density too high** - Please check the value (max: 50 g/cm³)")
                    
                    # Display validation errors
                    if validation_errors:
                        st.error("**Please fix the following issues:**")
                        for error in validation_errors:
                            st.error(error)
                    else:
                        try:
                            compound.name = name.strip()
                            compound.formula = formula.strip() if formula else None
                            compound.cas_number = cas_number.strip() if cas_number else None
                            compound.molecular_weight = molecular_weight if molecular_weight > 0 else None
                            compound.density = density if density > 0 else None
                            compound.melting_point = melting_point if melting_point != 0 else None
                            compound.boiling_point = boiling_point if boiling_point != 0 else None
                            compound.supplier = supplier.strip() if supplier else None
                            compound.catalog_number = catalog_number.strip() if catalog_number else None
                            compound.notes = notes.strip() if notes else None
                            
                            db_session.commit()
                            st.success("✅ Compound updated successfully!")
                            st.session_state.edit_compound_id = None
                            st.rerun()
                            
                        except Exception as e:
                            db_session.rollback()
                            logger.error(f"Error updating compound: {e}")
                            
                            # Provide specific error messages for update failures
                            if "UNIQUE constraint failed" in str(e):
                                if "name" in str(e).lower():
                                    st.error("❌ **Duplicate Name Error**: Another compound with this name already exists. Please choose a different name.")
                                elif "cas_number" in str(e).lower():
                                    st.error("❌ **Duplicate CAS Number Error**: Another compound with this CAS number already exists. Please check the CAS number or leave it blank.")
                                else:
                                    st.error("❌ **Duplicate Data Error**: Some of the provided information already exists in the database. Please check for duplicates.")
                            elif "NOT NULL constraint failed" in str(e):
                                st.error("❌ **Required Field Error**: One or more required fields are missing. Please fill in all mandatory fields.")
                            elif "FOREIGN KEY constraint failed" in str(e):
                                st.error("❌ **Database Relationship Error**: There's an issue with database relationships. Please try again or contact support.")
                            elif "database is locked" in str(e).lower():
                                st.error("❌ **Database Locked Error**: The database is currently in use. Please wait a moment and try again.")
                            elif "permission denied" in str(e).lower():
                                st.error("❌ **Permission Error**: You don't have permission to update this compound. Contact your administrator.")
                            elif "disk full" in str(e).lower() or "no space left" in str(e).lower():
                                st.error("❌ **Storage Error**: Insufficient disk space. Please free up space and try again.")
                            else:
                                st.error(f"❌ **Update Error**: Failed to update compound. Error details: {str(e)}")
                            
                            # Show troubleshooting tips for updates
                            with st.expander("🔧 Troubleshooting Tips", expanded=False):
                                st.markdown("""
                                **If update fails:**
                                - Check that all required fields are filled
                                - Ensure compound names and CAS numbers are unique
                                - Verify you have permission to edit this compound
                                - Try refreshing the page and attempting again
                                - Contact support if the problem persists
                                """)
            
            with col2:
                if st.form_submit_button("❌ Cancel"):
                    st.session_state.edit_compound_id = None
                    st.rerun()
    
    except Exception as e:
        logger.error(f"Error in edit compound form: {e}")
        
        # Provide specific error messages for edit form loading failures
        if "no such table" in str(e).lower():
            st.error("❌ **Database Schema Error**: The compound tables don't exist. Please run database migrations.")
        elif "database is locked" in str(e).lower():
            st.error("❌ **Database Locked Error**: The database is currently in use. Please wait a moment and try again.")
        elif "permission denied" in str(e).lower():
            st.error("❌ **Permission Error**: You don't have permission to edit compounds. Contact your administrator.")
        elif "connection" in str(e).lower():
            st.error("❌ **Connection Error**: Unable to connect to the database. Please check your connection and try again.")
        else:
            st.error(f"❌ **Loading Error**: Failed to load edit form. Error details: {str(e)}")
        
        # Show troubleshooting tips for edit form errors
        with st.expander("🔧 Troubleshooting Tips", expanded=False):
            st.markdown("""
            **If the edit form fails to load:**
            - Check your internet connection
            - Ensure the database is accessible
            - Try refreshing the page
            - Contact support if the problem persists
            """)
    
    finally:
        db_session.close()

# Legacy functions for backward compatibility (simplified)
def render_chemical_additives_form(experiment_id: str, experiment_fk: int) -> List[Dict]:
    """Legacy function - redirects to compound management"""
    st.info("🧪 This functionality has been moved to the Compound Management page.")
    st.markdown("**Please use the Compound Management page to manage chemical compounds.**")
    return []

def save_chemical_additives(experiment_fk: int, additives_data: List[Dict]) -> bool:
    """Legacy function - not implemented"""
    st.warning("This functionality is not available in Compound Management mode.")
    return False

def validate_chemical_additives(additives_data: List[Dict]) -> List[str]:
    """Legacy function - not implemented"""
    return []