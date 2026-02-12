import os
import json
import argparse
from typing import Dict, Any, List
from database.supabase_client import get_supabase_client
from ui.db_export import generate_db_export
from models.schema import Series
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def populate_supabase(series: Series, championship_id: str):
    """
    Transform and UPSERT series data into Supabase.
    """
    client = get_supabase_client()
    if not client:
        print("❌ Supabase client not initialized. Check your .env file.")
        return

    print(f"🔄 Preparing data for championship: {series.name} ({championship_id})")
    export_data = generate_db_export(series, championship_id)

    # 1. UPSERT Circuits
    print(f"🏟️ Upserting {len(export_data['circuits'])} circuits...")
    for circuit in export_data['circuits']:
        client.table("circuits").upsert(circuit).execute()

    # 2. UPSERT Championship (Update metadata if needed)
    # Note: The mapping logic in db_export.py sets championship_row['id'] to championship_id
    print(f"🏆 Updating championship: {championship_id}")
    for champ in export_data['championships']:
        # We don't want to overwrite everything, maybe just some fields if needed
        # But for now, let's just make sure it exists or update basic info
        client.table("championships").upsert(champ).execute()

    # 3. UPSERT Events
    print(f"📅 Upserting {len(export_data['championship_events'])} events...")
    for event in export_data['championship_events']:
        client.table("championship_events").upsert(event).execute()

    # 4. UPSERT Sessions
    print(f"🏎️ Upserting {len(export_data['championship_event_sessions'])} sessions...")
    # It might be faster to batch upsert sessions if there are many
    if export_data['championship_event_sessions']:
        client.table("championship_event_sessions").upsert(export_data['championship_event_sessions']).execute()

    print("✅ Supabase population complete!")

def main():
    parser = argparse.ArgumentParser(description="Populate Supabase with motorsport data.")
    parser.add_argument("file", help="Path to the source JSON file.")
    parser.add_argument("championship_id", help="The UUID of the championship in Supabase.")
    
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        return

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Handle both raw series data and manifest-wrapped data
        if "manifest" in data and "series" in data:
            series_data = data["series"]
        else:
            series_data = data
            
        series = Series.from_dict(series_data)
        populate_supabase(series, args.championship_id)
        
    except Exception as e:
        print(f"❌ Error during population: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
