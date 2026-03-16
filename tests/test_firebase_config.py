import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import auth

def test_firebase_config():
    # Load environment variables
    load_dotenv()
    
    # Print environment variables (with sensitive data masked)
    print("\nChecking environment variables:")
    required_vars = [
        "FIREBASE_PROJECT_ID",
        "FIREBASE_PRIVATE_KEY_ID",
        "FIREBASE_PRIVATE_KEY",
        "FIREBASE_CLIENT_EMAIL",
        "FIREBASE_CLIENT_ID",
        "FIREBASE_CLIENT_CERT_URL"
    ]
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if var == "FIREBASE_PRIVATE_KEY":
                print(f"✓ {var}: [PRIVATE KEY PRESENT]")
            else:
                # Show first and last 4 characters only
                masked_value = value[:4] + "..." + value[-4:] if len(value) > 8 else "[PRESENT]"
                print(f"✓ {var}: {masked_value}")
        else:
            print(f"✗ {var}: Missing!")

    print("\nTesting Firebase connection:")
    try:
        # Try to initialize Firebase
        cred = firebase_admin.credentials.Certificate({
            "type": "service_account",
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
        })
        
        # Initialize the app
        try:
            firebase_admin.initialize_app(cred)
            print("✓ Firebase initialization successful")
        except ValueError:
            print("✓ Firebase already initialized")
            
        # Test listing users (requires proper authentication)
        auth.list_users()
        print("✓ Firebase authentication successful")
        
        print("\nAll tests passed! Your Firebase configuration is working correctly.")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        print("\nPlease check your Firebase configuration and try again.")

if __name__ == "__main__":
    test_firebase_config() 