"""
Repository for interacting with Supabase data.
Handles fetching reference data, staging drafts, and publishing changes.
"""

import os
import pandas as pd
import streamlit as st
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID, uuid4
from datetime import datetime
import json
from supabase import Client

from models.db_schema import (
    Championship, 
    Circuit, 
    ChampionshipEvent, 
    ChampionshipEventSession
)
from database.supabase_client import get_supabase_client

# Local CSV paths for offline/fallback
LOCAL_CHAMPIONSHIPS_CSV = "championships_rows.csv"
LOCAL_CIRCUITS_CSV = "circuits_rows.csv"

class Repository:
    def __init__(self):
        self.supabase: Optional[Client] = get_supabase_client()
        
    def get_championships(self) -> pd.DataFrame:
        """Fetch championships from Supabase or fallback to local CSV."""
        if self.supabase:
            try:
                response = self.supabase.table("championships").select("*").execute()
                df = pd.DataFrame(response.data)
                if not df.empty:
                    return df
            except Exception as e:
                print(f"Supabase fetch failed: {e}")
        
        # Fallback
        if os.path.exists(LOCAL_CHAMPIONSHIPS_CSV):
            return pd.read_csv(LOCAL_CHAMPIONSHIPS_CSV)
        return pd.DataFrame()

    def get_circuits(self) -> pd.DataFrame:
        """Fetch circuits from Supabase or fallback to local CSV."""
        if self.supabase:
            try:
                # Retrieve all circuits (might need pagination in production if list grows large)
                response = self.supabase.table("circuits").select("*").execute()
                df = pd.DataFrame(response.data)
                if not df.empty:
                    return df
            except Exception as e:
                print(f"Supabase fetch failed: {e}")
        
        # Fallback
        if os.path.exists(LOCAL_CIRCUITS_CSV):
            return pd.read_csv(LOCAL_CIRCUITS_CSV)
        return pd.DataFrame()

    def stage_data(
        self, 
        events: pd.DataFrame, 
        sessions: pd.DataFrame
    ) -> str:
        """
        Write draft events and sessions to staging tables.
        Returns an import_id or a success message.
        """
        if not self.supabase:
            raise ConnectionError("Supabase not connected. Cannot stage data.")

        import_id = str(uuid4())
        
        # Prepare events for staging
        stg_events = events.copy()
        stg_events["import_id"] = import_id
        # Ensure dates/metadata are serialized correctly
        records_events = stg_events.to_dict(orient="records")
        # Remove None/NaN values effectively 
        cleaned_events = []
        for r in records_events:
            # Exclude UI-only columns and empty values
            clean_r = {
                k: v for k, v in r.items() 
                if pd.notna(v) and v != "" and k not in ["circuit_name"]
            }
            
            # Ensure dates are strings for JSON serialization
            if "start_date" in clean_r and hasattr(clean_r["start_date"], "isoformat"):
                clean_r["start_date"] = clean_r["start_date"].isoformat()
            if "end_date" in clean_r and hasattr(clean_r["end_date"], "isoformat"):
                clean_r["end_date"] = clean_r["end_date"].isoformat()
                
            cleaned_events.append(clean_r)

        # Prepare sessions for staging
        stg_sessions = sessions.copy()
        
        # Recombine Naive Time + Offset -> ISO String if offsets exist
        # This handles the UI "Local Time" display logic
        if "start_time_offset" in stg_sessions.columns:
            def combine_time(row, col_name):
                t = row.get(col_name)
                off = row.get(f"{col_name}_offset")
                
                if pd.isna(t) or t == "":
                    return None
                    
                # If t is already a string (ISO), assume it's good? 
                # But it might be the naive string from editor.
                # If t is datetime/Timestamp
                if isinstance(t, pd.Timestamp) or isinstance(t, datetime):
                    t_str = t.isoformat()
                else:
                    t_str = str(t)
                    
                # If offset is present, append it
                if pd.notna(off) and off:
                    # If t_str already has offset? Naive usually doesn't.
                    # Just append space/offset
                    # ISO format: YYYY-MM-DDTHH:MM:SS+HH:MM
                    return f"{t_str}{off}"
                else:
                    # Fallback to UTC assumption if no offset provided
                    return f"{t_str}Z"

            stg_sessions["start_time"] = stg_sessions.apply(lambda r: combine_time(r, "start_time"), axis=1)
            stg_sessions["end_time"] = stg_sessions.apply(lambda r: combine_time(r, "end_time"), axis=1)

        stg_sessions["import_id"] = import_id
        records_sessions = stg_sessions.to_dict(orient="records")
        cleaned_sessions = []
        for r in records_sessions:
            # Exclude offset columns from DB insert
            clean_r = {
                k: v for k, v in r.items() 
                if pd.notna(v) and v != "" and not k.endswith("_offset")
            }
            cleaned_sessions.append(clean_r)

        # Write to Supabase Staging Tables (assuming they exist as stg_championship_events etc)
        # Note: If stg tables don't exist per prompt we might need to fake it or use a specific strategy.
        # The prompt says: "Write the edited draft rows to staging tables: stg_championship_events, stg_championship_event_sessions"
        
        try:
            self.supabase.table("stg_championship_events").insert(cleaned_events).execute()
            self.supabase.table("stg_championship_event_sessions").insert(cleaned_sessions).execute()
        except Exception as e:
            # If staging tables don't exist, we might fail here. 
            # Ideally we'd warn the user.
            raise e
            
        return import_id

    def get_staged_data(self, import_id: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Read back staged data for verification."""
        if not self.supabase:
            return pd.DataFrame(), pd.DataFrame()
            
        try:
            e_res = self.supabase.table("stg_championship_events").select("*").eq("import_id", import_id).execute()
            s_res = self.supabase.table("stg_championship_event_sessions").select("*").eq("import_id", import_id).execute()
            
            return pd.DataFrame(e_res.data), pd.DataFrame(s_res.data)
        except Exception as e:
            st.error(f"Failed to read staging: {e}")
            return pd.DataFrame(), pd.DataFrame()

    def clear_staging(self, import_id: str):
        """Cleanup staging tables."""
        if not self.supabase:
            return
        self.supabase.table("stg_championship_event_sessions").delete().eq("import_id", import_id).execute()
        self.supabase.table("stg_championship_events").delete().eq("import_id", import_id).execute()

    def publish_events(self, events: List[Dict[str, Any]]) -> Dict[Tuple[int, int], str]:
        """
        Upsert events and return a mapping of (season, round) -> event_id.
        """
        if not self.supabase:
            raise ConnectionError("Supabase disconnected")

        lookup_map = {}
        
        for evt in events:
            # We must NOT send 'id' or 'import_id' for the upsert to work correctly 
            # with the unique constraint on (championship_id, season, round_number).
            # If we send 'id=None', Supabase might error.
            
            payload = {
                k: v for k, v in evt.items() 
                if k not in ["id", "import_id", "temp_id", "circuit_name"] and v is not None
            }
            
            try:
                # Upsert based on unique constraint: championship_id, season, round_number
                # We need column names for on_conflict
                res = self.supabase.table("championship_events").upsert(
                    payload, 
                    on_conflict="championship_id,season,round_number"
                ).execute()
                
                # print(f"DEBUG: Upsert res for round {evt.get('round_number')}: {res}")
                
                if res.data:
                    outcome = res.data[0]
                    key = (outcome["season"], outcome["round_number"])
                    lookup_map[key] = outcome["id"]
                else:
                    print(f"DEBUG: No data returned for round {evt.get('round_number')}")
                    
            except Exception as e:
                print(f"Error publishing event round {evt.get('round_number')}: {e}")
                
        if lookup_map:
            k_sample = list(lookup_map.keys())[0]
            print(f"DEBUG: lookup_map sample key: {k_sample} (Type: {type(k_sample[0])}, {type(k_sample[1])})")
            print(f"DEBUG: lookup_map size: {len(lookup_map)}")
        else:
            print("DEBUG: lookup_map is empty!")
            
        return lookup_map

    def publish_sessions(self, sessions: List[Dict[str, Any]], event_map: Dict[Tuple[int, int], str], season: int) -> Tuple[int, int]:
        """
        Upsert sessions linking them to the correct parent event.
        Logic:
        1. Resolve parent event_id using (season, round_number) from session.
        2. Match by (championship_event_id, session_type, start_time).
        """
        if not self.supabase:
            return 0, 0

        cnt_insert = 0
        cnt_update = 0
        
        print(f"DEBUG: publish_sessions called with season={season} (Type: {type(season)})")
        
        for sess in sessions:
            # Resolve parent
            parent_round = sess.get("parent_round")
            if parent_round is None:
                print(f"Skipping session {sess.get('name')} - no parent round")
                continue
            
            # Debug match
            key = (season, parent_round)
            event_id = event_map.get(key)
            
            if not event_id:
                # Try casting round to int if it's float/str
                try:
                    alt_key = (int(season), int(parent_round))
                    event_id = event_map.get(alt_key)
                except:
                    pass
            
            if not event_id:
                print(f"DEBUG: Orphan session. Key: {key}. Map has {len(event_map)} keys.")
                # print(f"DEBUG: Map keys: {list(event_map.keys())}")
                continue
                
            # Prepare payload
            payload = {
                "championship_event_id": event_id,
                "name": sess["name"],
                "session_type": sess["session_type"],
                "start_time": sess.get("start_time"),
                "end_time": sess.get("end_time"),
                "is_cancelled": sess.get("is_cancelled", False)
            }
            
            # Remove keys that shouldn't be in the payload
            # (start_time/end_time handled above, strict typing matters)
            
            # Idempotency check
            # We check if a session exists with same Event + Type + StartTime
            query = self.supabase.table("championship_event_sessions") \
                .select("id") \
                .eq("championship_event_id", event_id) \
                .eq("session_type", sess["session_type"])
            
            if sess.get("start_time"):
                query = query.eq("start_time", sess["start_time"])
            
            # Execute check
            existing = query.execute()
            
            if existing.data:
                # Update existing session
                sid = existing.data[0]["id"]
                payload["updated_at"] = datetime.now().isoformat()
                
                self.supabase.table("championship_event_sessions") \
                    .update(payload) \
                    .eq("id", sid) \
                    .execute()
                cnt_update += 1
            else:
                # Insert new session (DB generates ID)
                self.supabase.table("championship_event_sessions") \
                    .insert(payload) \
                    .execute()
                cnt_insert += 1
                
        return cnt_insert, cnt_update

    def get_events(self, championship_id: str, season: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch production events and sessions for a given championship season."""
        if not self.supabase:
            return pd.DataFrame(), pd.DataFrame()
            
        try:
            # Fetch events
            e_res = self.supabase.table("championship_events") \
                .select("*") \
                .eq("championship_id", championship_id) \
                .eq("season", season) \
                .execute()
                
            e_df = pd.DataFrame(e_res.data)
            
            s_df = pd.DataFrame()
            if not e_df.empty:
                # Fetch sessions for these events
                event_ids = e_df["id"].tolist()
                # Supabase 'in' filter is .in_("column", [list])
                s_res = self.supabase.table("championship_event_sessions") \
                    .select("*") \
                    .in_("championship_event_id", event_ids) \
                    .execute()
                s_df = pd.DataFrame(s_res.data)
                
            return e_df, s_df
            
        except Exception as e:
            st.error(f"Failed to fetch production data: {e}")
            return pd.DataFrame(), pd.DataFrame()
