import firebase_admin
from firebase_admin import auth
from typing import Optional, Dict
from firebase_admin import firestore
import datetime
import secrets

def create_user(email: str, password: str, display_name: Optional[str] = None) -> Dict:
    """
    Create a new user in Firebase.
    
    Args:
        email (str): User's email address (must end with @addisenergy.com)
        password (str): User's password
        display_name (str, optional): User's display name
        
    Returns:
        Dict: User information if successful
        
    Raises:
        ValueError: If email doesn't end with @addisenergy.com
        Exception: If user creation fails
    """
    if not email.lower().endswith('@addisenergy.com'):
        raise ValueError("Email must end with @addisenergy.com")
    
    try:
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name or email.split('@')[0]
        )
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'created_at': user.user_metadata.creation_timestamp
        }
    except Exception as e:
        raise Exception(f"Failed to create user: {str(e)}")

def list_users() -> list:
    """
    List all users in Firebase.
    
    Returns:
        list: List of user dictionaries
    """
    try:
        users = auth.list_users()
        return [{
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'created_at': user.user_metadata.creation_timestamp,
            'disabled': user.disabled,
            'custom_claims': user.custom_claims or {}
        } for user in users.users]
    except Exception as e:
        raise Exception(f"Failed to list users: {str(e)}")

def delete_user(uid: str) -> bool:
    """
    Delete a user from Firebase.
    
    Args:
        uid (str): User's UID
        
    Returns:
        bool: True if successful
        
    Raises:
        Exception: If user deletion fails
    """
    try:
        auth.delete_user(uid)
        return True
    except Exception as e:
        raise Exception(f"Failed to delete user: {str(e)}")

def update_user(uid: str, display_name: Optional[str] = None, email: Optional[str] = None) -> Dict:
    """
    Update a user's information in Firebase.
    
    Args:
        uid (str): User's UID
        display_name (str, optional): New display name
        email (str, optional): New email (must end with @addisenergy.com)
        
    Returns:
        Dict: Updated user information
        
    Raises:
        ValueError: If new email doesn't end with @addisenergy.com
        Exception: If update fails
    """
    if email and not email.lower().endswith('@addisenergy.com'):
        raise ValueError("Email must end with @addisenergy.com")
    
    try:
        updates = {}
        if display_name:
            updates['display_name'] = display_name
        if email:
            updates['email'] = email
            
        user = auth.update_user(uid, **updates)
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'created_at': user.user_metadata.creation_timestamp
        }
    except Exception as e:
        raise Exception(f"Failed to update user: {str(e)}")

def create_pending_user_request(email: str, display_name: str, role: str) -> Dict:
    """Create a pending user request in Firestore.

    No password is collected or stored: the user sets one via the setup link
    generated at approval time (see approve_user).
    """
    db = firestore.client()

    # Check if request already exists
    existing_request = db.collection('pending_users').where('email', '==', email).get()
    if existing_request:
        raise ValueError("A request for this email already exists.")

    # Create pending user document
    pending_user = {
        'email': email,
        'display_name': display_name,
        'role': role,
        'status': 'pending',
        'created_at': datetime.datetime.now(),
        'updated_at': datetime.datetime.now()
    }
    
    db.collection('pending_users').add(pending_user)
    return pending_user

def list_pending_users() -> list:
    """List all pending user requests."""
    db = firestore.client()
    pending_users = db.collection('pending_users').where('status', '==', 'pending').get()
    return [{**doc.to_dict(), 'id': doc.id} for doc in pending_users]

def approve_user(request_id: str) -> Dict:
    """Approve a pending user request.

    Creates the Firebase Auth user with a random throwaway password (any password
    stored on a legacy request is ignored), sets the ``approved``/``role`` claims,
    deletes the request's ``password`` field, and returns the user dict plus
    ``role`` and ``password_setup_link`` (a password-reset link the admin sends to
    the user; ``None`` if link generation failed).
    """
    db = firestore.client()

    # Get the pending request
    request_ref = db.collection('pending_users').document(request_id)
    request = request_ref.get()

    if not request.exists:
        raise ValueError("Request not found.")

    request_data = request.to_dict()

    # Create the user in Firebase Auth
    user = create_user(
        email=request_data['email'],
        password=secrets.token_urlsafe(32),
        display_name=request_data['display_name']
    )

    # Set custom claims for the user
    auth.set_custom_user_claims(user['uid'], {
        'approved': True,
        'role': request_data['role']
    })

    # Update request status; drop any plaintext password left by the old flow
    request_ref.update({
        'status': 'approved',
        'password': firestore.DELETE_FIELD,
        'updated_at': datetime.datetime.now(),
        'approved_at': datetime.datetime.now()
    })

    try:
        setup_link: Optional[str] = auth.generate_password_reset_link(request_data['email'])
    except Exception:
        setup_link = None  # caller (CLI) tells the admin to run reset-password

    return {**user, 'role': request_data['role'], 'password_setup_link': setup_link}

def purge_pending_passwords() -> int:
    """Delete the ``password`` field from every pending_users document.

    Returns the number of documents changed.
    """
    db = firestore.client()
    changed = 0
    for doc in db.collection('pending_users').stream():
        if 'password' in (doc.to_dict() or {}):
            doc.reference.update({'password': firestore.DELETE_FIELD})
            changed += 1
    return changed

def reject_user(request_id: str, reason: str = None) -> bool:
    """Reject a pending user request."""
    db = firestore.client()
    
    request_ref = db.collection('pending_users').document(request_id)
    if not request_ref.get().exists:
        raise ValueError("Request not found.")
        
    # Delete the request instead of marking it as rejected
    request_ref.delete()
    
    return True

def delete_request_by_email(email: str) -> bool:
    """Delete any existing requests for a specific email."""
    db = firestore.client()
    
    # Query for any documents with this email
    requests = db.collection('pending_users').where('email', '==', email).get()
    
    if not requests:
        return False
        
    # Delete all matching documents
    for request in requests:
        request.reference.delete()
    
    return True

def set_user_claims(uid: str, role: str = "user") -> Dict:
    """Set custom claims for an existing user."""
    try:
        # Set custom claims for the user
        auth.set_custom_user_claims(uid, {
            'approved': True,
            'role': role
        })
        
        # Get the updated user
        user = auth.get_user(uid)
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'custom_claims': user.custom_claims
        }
    except Exception as e:
        raise Exception(f"Failed to set user claims: {str(e)}")

def reset_user_password(email: str) -> str:
    """
    Generate a password reset link for the given email.
    
    Args:
        email (str): The user's email address.
        
    Returns:
        str: The password reset link.
        
    Raises:
        Exception: If the link generation fails.
    """
    try:
        link = auth.generate_password_reset_link(email)
        return link
    except Exception as e:
        raise Exception(f"Failed to generate password reset link: {str(e)}") 