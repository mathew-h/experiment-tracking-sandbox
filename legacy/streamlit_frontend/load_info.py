from database import SessionLocal, SampleInfo, ExternalAnalysis, PXRFReading
import streamlit as st
from frontend.config.variable_config import ROCK_SAMPLE_CONFIG, PXRF_ELEMENT_COLUMNS
from sqlalchemy.orm import selectinload
import pandas as pd

def get_sample_info(sample_id):
    """
    Retrieve detailed information about a specific rock sample.
    
    Args:
        sample_id (str): The unique identifier of the sample to retrieve
        
    Returns:
        dict: Dictionary containing sample information with fields defined in ROCK_SAMPLE_CONFIG
    """
    try:
        db = SessionLocal()
        sample_info = db.query(SampleInfo).filter(SampleInfo.sample_id == sample_id).first()
        
        if sample_info:
            # Create dictionary using field names from ROCK_SAMPLE_CONFIG
            return {
                field: getattr(sample_info, field)
                for field in ROCK_SAMPLE_CONFIG.keys()
            }
        return None
    except Exception as e:
        st.error(f"Error retrieving sample information: {str(e)}")
        return None
    finally:
        db.close()

def get_external_analyses(sample_id, db=None):
    """
    Retrieve all external analyses associated with a rock sample, including parsed pXRF data.
    
    Args:
        sample_id (str): The unique identifier of the sample
        db (Session, optional): SQLAlchemy session to use. If None, creates a new session.
        
    Returns:
        list: List of dictionaries containing analysis information. 
              For pXRF analyses, includes an additional 'pxrf_readings' key 
              containing a list of dictionaries for each reading from the database.
    """
    should_close_db = False
    if db is None:
        db = SessionLocal()
        should_close_db = True

    try:
        analyses_query = db.query(ExternalAnalysis).options(
            selectinload(ExternalAnalysis.analysis_files)
        ).filter(ExternalAnalysis.sample_id == sample_id).all()

        results = []
        for analysis in analyses_query:
            analysis_dict = {
                'id': analysis.id,
                'analysis_type': analysis.analysis_type,
                'analysis_files': [{
                    'id': file.id,
                    'file_path': file.file_path,
                    'file_name': file.file_name,
                    'file_type': file.file_type
                } for file in analysis.analysis_files],
                'analysis_date': analysis.analysis_date,
                'laboratory': analysis.laboratory,
                'analyst': analysis.analyst,
                'pxrf_reading_no': analysis.pxrf_reading_no,
                'description': analysis.description,
                'analysis_metadata': analysis.analysis_metadata,
                'created_at': analysis.created_at,
                'updated_at': analysis.updated_at,
                'pxrf_readings': []
            }

            if analysis.analysis_type == 'pXRF' and analysis.pxrf_reading_no:
                reading_numbers_list = [num.strip() for num in analysis.pxrf_reading_no.split(',') if num.strip()]
                if reading_numbers_list:
                    pxrf_data_query = db.query(PXRFReading).filter(
                        PXRFReading.reading_no.in_(reading_numbers_list)
                    ).all()
                    
                    pxrf_readings_list = []
                    for reading in pxrf_data_query:
                        reading_dict = {
                            'reading_no': reading.reading_no,
                            **{col.lower(): getattr(reading, col.lower(), None) for col in PXRF_ELEMENT_COLUMNS}
                        }
                        pxrf_readings_list.append(reading_dict)
                    analysis_dict['pxrf_readings'] = pxrf_readings_list

            results.append(analysis_dict)
            
        return results
    except Exception as e:
        st.error(f"Error retrieving external analyses: {str(e)}")
        return []
    finally:
        if should_close_db:
            db.close()