import os
import streamlit as st
from supabase import create_client, Client

# Initialize Supabase client
@st.cache_resource
def init_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    # Prefer SUPABASE_KEY (anon), fallback to SERVICE_ROLE if necessary but warn
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    
    if not url or not key:
        return None
        
    return create_client(url, key)

def is_login_required():
    """Check if login is required based on environment variable."""
    # Default to True if not specified
    return os.environ.get("REQUIRE_LOGIN", "true").lower() == "true"

def login_form():
    """Render the login form."""
    st.markdown("""
        <style>
            .login-container {
                padding: 2rem;
                background: rgba(255,255,255,0.05);
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,0.1);
            }
        </style>
    """, unsafe_allow_html=True)

    st.title("🏁 Login")

    # Center the login form
    _, col, _ = st.columns([1, 1, 1])
    
    with col:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In", use_container_width=True)
            
        if submit:
            # Dev bypass
            test_user = os.environ.get("TEST_USERNAME")
            test_pass = os.environ.get("TEST_PASSWORD")
            
            if test_user and test_pass and email == test_user and password == test_pass:
                st.session_state.user = {"id": "dev-test-user", "email": f"{test_user}@example.com"}
                st.session_state.auth_token = "dev-token"
                st.success("Logged in as Test User!")
                st.rerun()
                return

            supabase = init_supabase()
            if not supabase:
                st.error("Supabase configuration missing in .env")
                return
            
            try:
                res = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                st.session_state.user = res.user
                st.session_state.auth_token = res.session.access_token
                st.success("Logged in successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {str(e)}")

def check_auth():
    """
    Main auth check function. 
    Returns True if user can proceed (either logged in or login not required).
    Returns False if user needs to log in (and renders login form).
    """
    if not is_login_required():
        return True
        
    if "user" in st.session_state and st.session_state.user:
        return True
        
    login_form()
    return False

def logout():
    """Sign out the current user."""
    supabase = init_supabase()
    if supabase:
        supabase.auth.sign_out()
    
    if "user" in st.session_state:
        del st.session_state.user
    if "auth_token" in st.session_state:
        del st.session_state.auth_token
        
    st.rerun()
