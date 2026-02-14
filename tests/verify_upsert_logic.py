import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime

# Adjust path to import from project root
import sys
import os
sys.path.append(os.getcwd())

from database.repository import Repository

class TestUpsertLogic(unittest.TestCase):
    
    def setUp(self):
        # Mock Supabase client
        self.mock_client = MagicMock()
        
        # Patch the get_supabase_client to return our mock
        patcher = patch('database.repository.get_supabase_client', return_value=self.mock_client)
        self.mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        
        self.repo = Repository()

    def test_publish_events_upsert(self):
        """Test that publish_events calls upsert with correct logic."""
        # Setup input
        events = [
            {
                "name": "Test Event",
                "championship_id": "champ_123",
                "season": 2026,
                "round_number": 1,
                "temp_id": 1, # Should be removed
                "id": None # Should be removed
            }
        ]
        
        # Mock upsert return
        mock_upsert = self.mock_client.table.return_value.upsert.return_value.execute
        mock_upsert.return_value.data = [{"id": "new_uuid_123", "season": 2026, "round_number": 1}]
        
        # Execute
        result_map = self.repo.publish_events(events)
        
        # Verify call arguments
        self.mock_client.table.assert_called_with("championship_events")
        args, kwargs = mock_upsert.call_args_list[0] if mock_upsert.called else (None, None)
        
        # In supabase-py, upsert is called on the table builder.
        # table("...").upsert(payload, on_conflict=...)
        self.mock_client.table("championship_events").upsert.assert_called()
        call_args = self.mock_client.table("championship_events").upsert.call_args
        payload = call_args[0][0]
        kwargs = call_args[1]
        
        # Check payload clean
        self.assertNotIn("id", payload)
        self.assertNotIn("temp_id", payload)
        self.assertEqual(payload["name"], "Test Event")
        
        # Check on_conflict
        self.assertEqual(kwargs.get("on_conflict"), "championship_id,season,round_number")
        
        # Check result map
        self.assertEqual(result_map[(2026, 1)], "new_uuid_123")
        
    def test_publish_sessions_insert(self):
        """Test that distinct sessions are inserted."""
        # Input
        sessions = [
            {
                "name": "FP1",
                "session_type": "practice",
                "start_time": "2026-03-01T10:00:00",
                "parent_round": 1
            }
        ]
        event_map = {(2026, 1): "evt_123"}
        
        # Mock select to return empty (no existing session)
        self.mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        
        # Execute
        cnt_ins, cnt_upd = self.repo.publish_sessions(sessions, event_map, 2026)
        
        # Verify
        self.assertEqual(cnt_ins, 1)
        self.assertEqual(cnt_upd, 0)
        self.mock_client.table("championship_event_sessions").insert.assert_called()
        
    def test_publish_sessions_update(self):
        """Test that existing sessions are updated."""
        # Input
        sessions = [
            {
                "name": "Race",
                "session_type": "race",
                "start_time": "2026-03-01T14:00:00",
                "parent_round": 1
            }
        ]
        event_map = {(2026, 1): "evt_123"}
        
        # Mock select to return existing row
        self.mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "existing_sess_id"}]
        
        # Execute
        cnt_ins, cnt_upd = self.repo.publish_sessions(sessions, event_map, 2026)
        
        # Verify
        self.assertEqual(cnt_ins, 0)
        self.assertEqual(cnt_upd, 1)
        self.mock_client.table("championship_event_sessions").update.assert_called()
        
        # Verify update call target
        call_args = self.mock_client.table("championship_event_sessions").update.call_args
        payload = call_args[0][0]
        # Should have updated_at
        self.assertIn("updated_at", payload)
        self.assertEqual(payload["name"], "Race")

if __name__ == '__main__':
    unittest.main()
