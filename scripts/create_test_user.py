import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Add parent directory to path to import local modules if needed, 
# but here we just need standard libs and supabase
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_test_user():
    load_dotenv()
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Need service role to admin create user or bypass confirmation if possible
    # Actually, for sign_up we can use the anon key, but we might need to confirm email.
    # If we use service role key, we can use admin_auth_client to create user with email confirmed.
    
    if not key:
        print("Error: SUPABASE_SERVICE_ROLE_KEY not found in .env")
        return

    supabase = create_client(url, key)
    
    email = "test@racebot.app"
    password = "password123"
    
    print(f"Attempting to create user: {email} / {password}")
    
    try:
        # Check if user exists (by trying to sign in?) Or just try to create.
        # admin.create_user auto-confirms email usually
        attributes = {
            "email": email,
            "password": password,
            "email_confirm": True
        }
        user = supabase.auth.admin.create_user(attributes)
        print(f"User created successfully! ID: {user.user.id}")
        print("\nCredentials:")
        print(f"Email: {email}")
        print(f"Password: {password}")
        
    except Exception as e:
        if "User already registered" in str(e) or "already exists" in str(e):
            print("User already exists. You can log in with:")
            print(f"Email: {email}")
            print(f"Password: {password}")
            # Consider updating password if needed, but for now just info
        else:
            print(f"Failed to create user: {e}")

if __name__ == "__main__":
    create_test_user()
