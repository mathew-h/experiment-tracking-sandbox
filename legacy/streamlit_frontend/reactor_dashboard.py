import streamlit as st
import pandas as pd
from database import SessionLocal
from database.models import Experiment, ExperimentalConditions, ExperimentStatus, ChemicalAdditive


def render_reactor_dashboard():
    """
    Render the reactor dashboard showing all 7 reactors with their currently assigned ONGOING experiments.
    
    Displays a table with columns:
    - Reactor Number (1-7)
    - Experiment ID
    - Sample ID
    - Description
    - Additives (formatted list)
    - Initial pH
    - Water Volume (mL)
    - Rock Mass (g)
    - Date
    """
    st.title("*Reactor Dashboard*")
    
    # Get database session
    db_session = SessionLocal()
    
    try:
        # Query all ONGOING experiments that have a reactor_number assigned
        # Join Experiment with ExperimentalConditions to access reactor_number
        ongoing_experiments = db_session.query(
            Experiment, 
            ExperimentalConditions
        ).join(
            ExperimentalConditions,
            Experiment.id == ExperimentalConditions.experiment_fk
        ).filter(
            Experiment.status == ExperimentStatus.ONGOING,
            ExperimentalConditions.reactor_number.isnot(None),
            ExperimentalConditions.experiment_type == "HPHT"
        ).all()
        
        # Create a mapping of reactor_number to experiment data
        reactor_map = {}
        for exp, conditions in ongoing_experiments:
            reactor_num = conditions.reactor_number
            if reactor_num is not None:
                # Format chemical additives list
                additives_str = ChemicalAdditive.format_additives_list(conditions.chemical_additives)
                
                reactor_map[reactor_num] = {
                    'experiment_id': exp.experiment_id,
                    'sample_id': exp.sample_id if exp.sample_id else '',
                    'description': exp.description if exp.description else '',
                    'additives': additives_str if additives_str else '',
                    'initial_ph': conditions.initial_ph if conditions.initial_ph is not None else '',
                    'water_volume_mL': conditions.water_volume_mL if conditions.water_volume_mL is not None else '',
                    'rock_mass_g': conditions.rock_mass_g if conditions.rock_mass_g is not None else '',
                    'date': exp.date.strftime('%Y-%m-%d') if exp.date else ''
                }
        
        # Build DataFrame with all 7 reactors
        reactor_data = []
        for reactor_num in range(1, 8):  # Reactors 1-7
            if reactor_num in reactor_map:
                # Reactor has an assigned ONGOING experiment
                exp_data = reactor_map[reactor_num]
                reactor_data.append({
                    'Reactor': reactor_num,
                    'Exp ID': exp_data['experiment_id'],
                    'Sample ID': exp_data['sample_id'],
                    'Additives': exp_data['additives'],
                    'Initial pH': exp_data['initial_ph'],
                    'Water (mL)': exp_data['water_volume_mL'],
                    'Rock (g)': exp_data['rock_mass_g'],
                    'Description': exp_data['description'],
                    'Date': exp_data['date']
                })
            else:
                # Reactor is unassigned
                reactor_data.append({
                    'Reactor': reactor_num,
                    'Exp ID': '',
                    'Sample ID': '',
                    'Additives': '',
                    'Initial pH': '',
                    'Water (mL)': '',
                    'Rock (g)': '',
                    'Description': '',
                    'Date': ''
                })
        
        # Build HTML table with embedded CSS that supports dark mode
        html = """
<style>
.reactor-dashboard-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 16px;
    margin: 10px 0;
    font-family: 'Source Sans Pro', sans-serif;
    color: inherit;
}
.reactor-dashboard-table th {
    background-color: rgba(128, 128, 128, 0.15);
    padding: 16px 12px;
    text-align: left;
    font-weight: 600;
    font-size: 18px;
    border-bottom: 2px solid rgba(128, 128, 128, 0.3);
}
.reactor-dashboard-table td {
    padding: 16px 12px;
    border-bottom: 1px solid rgba(128, 128, 128, 0.2);
    line-height: 1.6;
    vertical-align: center;
}
.reactor-dashboard-table tr:hover {
    background-color: rgba(128, 128, 128, 0.1);
}
.reactor-dashboard-table .empty-row {
    background-color: rgba(128, 128, 128, 0.05);
    opacity: 0.6;
}
.reactor-dashboard-table .reactor-col {
    width: 5%;
    text-align: center;
    font-weight: 600;
}
.reactor-dashboard-table .exp-id-col {
    width: 8%;
}
.reactor-dashboard-table .sample-id-col {
    width: 8%;
}
.reactor-dashboard-table .rock-col {
    width: 7%;
    text-align: center;
}
.reactor-dashboard-table .water-col {
    width: 7%;
    text-align: center;
}
.reactor-dashboard-table .ph-col {
    width: 7%;
    text-align: center;
}
.reactor-dashboard-table .additives-col {
    width: 15%;
    max-width: 250px;
}
.reactor-dashboard-table .description-col {
    width: 23%;
}
.reactor-dashboard-table .date-col {
    width: 10%;
}
</style>

<table class="reactor-dashboard-table">
<thead>
    <tr>
        <th class="reactor-col">Reactor</th>
        <th class="exp-id-col">Exp ID</th>
        <th class="sample-id-col">Sample ID</th>
        <th class="rock-col">Rock (g)</th>
        <th class="water-col">Water (mL)</th>
        <th class="ph-col">Initial pH</th>
        <th class="additives-col">Additives</th>
        <th class="description-col">Description</th>
        <th class="date-col">Experiment Date</th>
    </tr>
</thead>
<tbody>
"""
        
        for row in reactor_data:
            is_empty = not row['Exp ID']
            row_class = ' class="empty-row"' if is_empty else ''
            
            # Format numeric values
            ph_val = f"{row['Initial pH']:.1f}" if row['Initial pH'] != '' else ''
            water_val = f"{row['Water (mL)']:.0f}" if row['Water (mL)'] != '' else ''
            rock_val = f"{row['Rock (g)']:.2f}" if row['Rock (g)'] != '' else ''
            
            html += f"""
    <tr{row_class}>
        <td class="reactor-col">{row['Reactor']}</td>
        <td class="exp-id-col">{row['Exp ID']}</td>
        <td class="sample-id-col">{row['Sample ID']}</td>
        <td class="rock-col">{rock_val}</td>
        <td class="water-col">{water_val}</td>
        <td class="ph-col">{ph_val}</td>
        <td class="additives-col">{row['Additives']}</td>
        <td class="description-col">{row['Description']}</td>
        <td class="date-col">{row['Date']}</td>
    </tr>
"""
        
        html += """
</tbody>
</table>
"""
        
        # Use st.html for proper HTML rendering
        st.html(html)
        
        # Display summary information
        assigned_count = sum(1 for r in reactor_data if r['Exp ID'])
        st.markdown(f"**{assigned_count} of 7 reactors currently assigned**")
        
    except Exception as e:
        st.error(f"Error loading reactor dashboard: {e}")
    
    finally:
        db_session.close()

