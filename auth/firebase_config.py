import firebase_admin
from firebase_admin import credentials, auth
import os
from dotenv import load_dotenv
import json
import streamlit as st

# Load environment variables
load_dotenv()

def get_secret_or_env(key, env_key):
    """Get value from Streamlit secrets or environment variables."""
    try:
        return st.secrets["FIREBASE"][key]
    except:
        return os.getenv(env_key)

# Get Firebase credentials from environment variables or Streamlit secrets
FIREBASE_PROJECT_ID = get_secret_or_env("PROJECT_ID", "FIREBASE_PROJECT_ID")
FIREBASE_PRIVATE_KEY = get_secret_or_env("PRIVATE_KEY", "FIREBASE_PRIVATE_KEY")
FIREBASE_CLIENT_EMAIL = get_secret_or_env("CLIENT_EMAIL", "FIREBASE_CLIENT_EMAIL")

# Client-side Firebase config
FIREBASE_CONFIG = {
    "apiKey": get_secret_or_env("API_KEY", "FIREBASE_API_KEY"),
    "authDomain": get_secret_or_env("AUTH_DOMAIN", "FIREBASE_AUTH_DOMAIN"),
    "projectId": FIREBASE_PROJECT_ID,
    "storageBucket": get_secret_or_env("STORAGE_BUCKET", "FIREBASE_STORAGE_BUCKET"),
    "messagingSenderId": get_secret_or_env("MESSAGING_SENDER_ID", "FIREBASE_MESSAGING_SENDER_ID"),
    "appId": get_secret_or_env("APP_ID", "FIREBASE_APP_ID"),
    "measurementId": get_secret_or_env("MEASUREMENT_ID", "FIREBASE_MEASUREMENT_ID"),
}

# Initialize Firebase Admin SDK
try:
    # Check if Firebase is already initialized
    if not firebase_admin._apps:
        # Create credentials from environment variables or secrets
        cred_dict = {
            "type": "service_account",
            "project_id": FIREBASE_PROJECT_ID,
            "private_key": FIREBASE_PRIVATE_KEY.replace('\\n', '\n'),
            "client_email": FIREBASE_CLIENT_EMAIL,
            "client_id": get_secret_or_env("CLIENT_ID", "FIREBASE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": get_secret_or_env("CLIENT_CERT_URL", "FIREBASE_CLIENT_CERT_URL")
        }
        
        # Initialize with credentials
        cred = credentials.Certificate(cred_dict)
        app = firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully with credentials")
    else:
        app = firebase_admin.get_app()
        print("Using existing Firebase app")
except Exception as e:
    print(f"Error initializing Firebase: {str(e)}")
    raise

def verify_token(token):
    """Verify Firebase token (either ID token or custom token)."""
    try:
        # First try to verify as ID token
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token
        except:
            # If ID token verification fails, try custom token
            decoded_token = auth.verify_id_token(token, check_revoked=False)
            return decoded_token
    except Exception as e:
        print(f"Error verifying token: {str(e)}")
        return None

def get_user_by_email(email):
    """Get user by email."""
    try:
        user = auth.get_user_by_email(email)
        return user
    except Exception as e:
        print(f"Error getting user by email: {str(e)}")
        return None

def get_firebase_config():
    """Get Firebase configuration for client-side."""
    return FIREBASE_CONFIG 