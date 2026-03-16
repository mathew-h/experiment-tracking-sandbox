import streamlit as st
import firebase_admin
from firebase_admin import auth
from auth.firebase_config import verify_token, get_firebase_config
from auth.user_management import create_pending_user_request
import requests

def validate_email_domain(email):
    """Validate that the email ends with @addisenergy.com"""
    return email.lower().endswith('@addisenergy.com')

def init_auth_state():
    """Initialize authentication state in session."""
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'auth_token' not in st.session_state:
        st.session_state.auth_token = None
    if 'firebase_config' not in st.session_state:
        st.session_state.firebase_config = get_firebase_config()

def render_login_page():
    """Render the login page."""
    st.title("Login")
    
    # Add tabs for Login and Register
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Login"):
                try:
                    # First validate email domain
                    if not validate_email_domain(email):
                        st.error("Access restricted to @addisenergy.com email addresses only.")
                        return

                    # Authenticate with Firebase REST API
                    api_key = st.session_state.firebase_config.get("apiKey")
                    if not api_key:
                        st.error("Firebase API key not found. Please check configuration.")
                        return

                    rest_api_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
                    payload = {
                        "email": email,
                        "password": password,
                        "returnSecureToken": True
                    }
                    
                    response = requests.post(rest_api_url, json=payload)
                    
                    if response.status_code == 200:
                        auth_data = response.json()
                        uid = auth_data['localId']
                        
                        # Check if user is approved
                        user = auth.get_user(uid)
                        if not user.custom_claims or not user.custom_claims.get('approved'):
                            st.error("Your account is pending approval. Please wait for admin approval.")
                            return
                        
                        st.session_state.user = {
                            'uid': user.uid,
                            'email': user.email,
                            'display_name': user.display_name or user.email
                        }
                        st.session_state.auth_token = auth_data['idToken']
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid email or password")
                except Exception as e:
                    st.error(f"Login failed: {str(e)}")
    
    with tab2:
        with st.form("register_form"):
            reg_email = st.text_input("Email (@addisenergy.com)")
            reg_password = st.text_input("Password", type="password")
            reg_confirm_password = st.text_input("Confirm Password", type="password")
            reg_display_name = st.text_input("Display Name")
            reg_role = st.text_input("Role")
            
            if st.form_submit_button("Request Account"):
                try:
                    # Validate email domain
                    if not validate_email_domain(reg_email):
                        st.error("Registration is restricted to @addisenergy.com email addresses only.")
                        return
                        
                    # Validate passwords match
                    if reg_password != reg_confirm_password:
                        st.error("Passwords do not match.")
                        return
                        
                    # Create pending user request
                    create_pending_user_request(
                        email=reg_email,
                        password=reg_password,
                        display_name=reg_display_name,
                        role=reg_role
                    )
                    st.success("Registration request submitted. Please wait for admin approval.")
                except Exception as e:
                    st.error(f"Registration failed: {str(e)}")

def require_auth(func):
    """Decorator to require authentication for a function."""
    def wrapper(*args, **kwargs):
        if not st.session_state.get('user'):
            st.warning("Please log in to access this feature.")
            render_login_page()
            return
        
        # Check email domain on every protected route
        if not validate_email_domain(st.session_state.user['email']):
            st.error("Access restricted to @addisenergy.com email addresses only.")
            render_login_page()
            return
            
        # Verify token on protected routes
        if st.session_state.get('auth_token'):
            try:
                verify_token(st.session_state.auth_token)
            except Exception as e:
                st.error("Session expired. Please log in again.")
                st.session_state.user = None
                st.session_state.auth_token = None
                render_login_page()
                return
                
        return func(*args, **kwargs)
    return wrapper

def render_logout_button():
    """Render the logout button."""
    if st.session_state.get('user'):
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.session_state.auth_token = None
            st.rerun() 