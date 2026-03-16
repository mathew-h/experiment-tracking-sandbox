import os
import base64
import streamlit as st

def render_header():
    # 1) Load & encode logo
    logo_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", ".streamlit", "static",
        "Addis_Avatar_SandColor_NoBackground.png"
    )
    with open(logo_path, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()

    # 2) Render header HTML + CSS
    st.markdown(f"""
    <div class="app-header">
      <img src="data:image/png;base64,{logo_b64}" class="app-logo" />
      <h1 class="app-title">Addis Energy Research</h1>
    </div>
    <hr class="app-divider"/>
    <style>
      /* overall header container */
      .app-header {{
        display: flex;
        align-items: center;
        padding: 40px 12px 0px;      /* lots of room up top so nothing gets cut off */
        margin-bottom: 0px;      /* tight space below before content */
      }}
      /* logo styling */
      .app-logo {{
        width: 56px;
        height: auto;
        margin-right: 16px;      /* gap between logo & title */
      }}
      /* title styling */
      .app-title {{
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.2;
        color: #FFFFFF;
      }}
      /* divider under the header */
      .app-divider {{
        border: none;
        border-top: 1px solid #444;
        margin: 0 0 0px 0 !important;    /* less space under divider */
      }}
      /* pull the main Streamlit container up under our divider */
      .block-container {{
        padding-top: 0 !important;
        margin-top: 0 !important;
      }}
    </style>
    """, unsafe_allow_html=True)
