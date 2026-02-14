import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def verify_login():
    load_dotenv()
    
    url = os.environ.get("SUPABASE_URL")
    # Use the ANON key for client-side login simulation
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    
    if not key:
        print("Error: SUPABASE_KEY (Anon) not found in .env")
        return

    print(f"Connecting to {url} with key starting with {key[:5]}...")
    supabase = create_client(url, key)
    
    email = "test@racebot.app"
    password = "password123"
    
    print(f"Attempting to sign in with: {email}")
    
    try:
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        print("Login SUCCESS!")
        print(f"User ID: {res.user.id}")
        print(f"Access Token: {res.session.access_token[:20]}...")
    except Exception as e:
        print(f"\nLogin FAILED!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        
        # Check if email is confirmed
        try:
             # Need service role to check user details via admin
            service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            if service_key:
                admin_client = create_client(url, service_key)
                user_res = admin_client.auth.admin.list_users()
                for u in user_res:
                    if u.email == email:
                        print(f"\nUser Details for {email}:")
                        print(f"ID: {u.id}")
                        print(f"Email Confirmed At: {u.email_confirmed_at}")
                        print(f"Phone Confirmed At: {u.phone_confirmed_at}")
                        print(f"Role: {u.role}")
                        break
        except Exception as admin_e:
            print(f"Could not fetch admin details: {admin_e}")

if __name__ == "__main__":
    verify_login()
