import streamlit as st
import pandas as pd
import io
from database import SessionLocal, Experiment, SampleInfo, ExperimentalConditions, ExperimentNotes, ExperimentalResults, ScalarResults, ExternalAnalysis, PXRFReading
from sqlalchemy import text, inspect

def download_database_as_excel():
    """
    Fetches data from specified tables and returns it as an Excel file
    in a BytesIO buffer.
    """
    db = SessionLocal()
    try:
        # Define tables to fetch and their corresponding models and sheet names
        tables_to_fetch = {
            "Experiments": Experiment,
            "ExperimentalConditions": ExperimentalConditions,
            "ExperimentNotes": ExperimentNotes,
            "ExperimentalResults": ExperimentalResults,
            "ScalarResults": ScalarResults,
            "SampleInfo": SampleInfo,
            "ExternalAnalyses": ExternalAnalysis,
            "PXRFReadings": PXRFReading,
        }

        inspector = inspect(db.get_bind())
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            sheets_written = 0
            for sheet_name, model in tables_to_fetch.items():
                table_name = model.__tablename__
                try:
                    if table_name not in inspector.get_table_names():
                        df_placeholder = pd.DataFrame({"Message": [f"Table {table_name} not found"]})
                        df_placeholder.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheets_written += 1
                        continue

                    columns = [col["name"] for col in inspector.get_columns(table_name)]
                    if not columns:
                        df_placeholder = pd.DataFrame({"Message": [f"No columns found for {table_name}"]})
                        df_placeholder.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheets_written += 1
                        continue

                    quoted_columns = ", ".join([f'"{col}"' for col in columns])
                    query = text(f'SELECT {quoted_columns} FROM "{table_name}"')
                    df = pd.read_sql_query(query, db.get_bind())

                    if df.empty:
                        df_placeholder = pd.DataFrame({"Message": [f"No data in {sheet_name} table"]})
                        df_placeholder.to_excel(writer, sheet_name=sheet_name, index=False)
                    else:
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                    sheets_written += 1
                except Exception as table_error:
                    df_placeholder = pd.DataFrame({"Message": [f"Failed to export {sheet_name}: {table_error}"]})
                    df_placeholder.to_excel(writer, sheet_name=sheet_name, index=False)
                    sheets_written += 1

            # Ensure at least one sheet exists
            if sheets_written == 0:
                pd.DataFrame({"Message": ["No data available"]}).to_excel(writer, sheet_name="Info", index=False)

        output.seek(0)  # Reset buffer position to the beginning
        return output
    except Exception as e:
        st.error(f"Error generating Excel file: {str(e)}")
        return None
    finally:
        db.close()

def render_sidebar():
    with st.sidebar:
        st.title("Navigation")
        page = st.radio(
            "Go to",
            ["Reactor Dashboard", "Bulk Uploads", "New Experiment", "View Experiments", 
             "New Rock Sample", "View Sample Inventory", "Compound Management", "Issue Submission"]
        )
         # Add some statistics or summary information
        st.markdown("---") # Separator
        st.markdown("### Quick Statistics")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            try:
                db = SessionLocal()
                total_experiments = db.query(Experiment).count()
                st.metric("Experiments", total_experiments)
            except Exception as e:
                st.error(f"Error retrieving experiment count: {str(e)}")
            finally:
                db.close()
        
        with col2:
            try:
                db = SessionLocal()
                # Use raw SQL to count samples without relying on the model
                result = db.execute(text("SELECT COUNT(*) FROM sample_info"))
                total_samples = result.scalar()
                
                # Check for duplicates
                result_unique = db.execute(text("""
                    SELECT COUNT(DISTINCT LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', '')))
                    FROM sample_info
                """))
                unique_samples = result_unique.scalar()
                
                duplicate_count = total_samples - unique_samples
                
                if duplicate_count > 0:
                    st.metric("Samples", total_samples, delta=f"-{duplicate_count} dups", delta_color="inverse")
                else:
                    st.metric("Samples", total_samples)
                    
            except Exception as e:
                st.error(f"Error retrieving sample count: {str(e)}")
            finally:
                db.close()
        
        with col3:
            try:
                db = SessionLocal()
                # Use raw SQL to count compounds without relying on the model
                result = db.execute(text("SELECT COUNT(*) FROM compounds"))
                total_compounds = result.scalar()
                st.metric("Compounds", total_compounds)
            except Exception as e:
                # If table doesn't exist yet, show 0 instead of error
                if "no such table" in str(e).lower():
                    st.metric("Compounds", 0)
                else:
                    st.error(f"Error retrieving compounds count: {str(e)}")
            finally:
                db.close()
        
        # Show duplicate warning if exists
        try:
            db = SessionLocal()
            result = db.execute(text("SELECT COUNT(*) FROM sample_info"))
            total_samples = result.scalar()
            result_unique = db.execute(text("""
                SELECT COUNT(DISTINCT LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', '')))
                FROM sample_info
            """))
            unique_samples = result_unique.scalar()
            duplicate_count = total_samples - unique_samples
            
            if duplicate_count > 0:
                with st.expander(f"⚠️ {duplicate_count} duplicate sample(s) detected", expanded=False):
                    st.warning(f"You have {duplicate_count} duplicate sample records. Click below to see details.")
                    
                    if st.button("Show Duplicate Details"):
                        # Query duplicate groups
                        result = db.execute(text("""
                            SELECT 
                                LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', '')) as normalized_id,
                                GROUP_CONCAT(sample_id, ', ') as variants,
                                COUNT(*) as count
                            FROM sample_info
                            GROUP BY LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', ''))
                            HAVING COUNT(*) > 1
                            ORDER BY count DESC
                            LIMIT 10
                        """))
                        
                        duplicates = result.fetchall()
                        if duplicates:
                            st.write("**Top duplicate groups:**")
                            for norm_id, variants, count in duplicates:
                                st.write(f"• {variants} ({count} copies)")
                            
                            if duplicate_count > 10:
                                st.info(f"...and {duplicate_count - 10} more")
                        
                        st.markdown("---")
                        st.markdown("**To fix:**")
                        st.code("python database/data_migrations/merge_duplicate_samples_007.py --apply", language="bash")
                        st.caption("This will merge duplicates and preserve all data. Run without --apply first to preview changes.")
        except Exception as e:
            pass  # Silently fail duplicate check to not disrupt sidebar
        finally:
            if 'db' in locals():
                db.close()

        st.markdown("---") # Separator
        
        excel_data = download_database_as_excel()
        if excel_data:
            st.download_button(
                label="Download Database as Excel",
                data=excel_data,
                file_name="database_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        return page