import os
from supabase import create_client, Client
from typing import Optional

def get_supabase_client() -> Optional[Client]:
    """
    Initialize and return a Supabase client using environment variables.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        return None

    return create_client(url, key)
