import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app import create_app
from app.db import get_db


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database_path = str(Path(self.temp_dir.name) / "test.sqlite")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": database_path,
            }
        )
        self.assertEqual(self.app.config["DATABASE"], database_path)
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.client = self.app.test_client()

    def test_home_route_responds_successfully(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"School IT Help Desk", response.data)
        self.assertIn(b'href="/tickets/new"', response.data)

    def test_health_route_responds_successfully(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_new_ticket_form_includes_all_required_fields(self):
        response = self.client.get("/tickets/new")

        self.assertEqual(response.status_code, 200)
        for field in ("room", "device", "category", "description", "priority"):
            self.assertRegex(
                response.get_data(as_text=True),
                rf'<(?:input|textarea|select)\b[^>]*name="{field}"[^>]*required',
            )
        self.assertIn(b'value="low"', response.data)
        self.assertIn(b'value="normal"', response.data)
        self.assertIn(b'value="high"', response.data)
        self.assertIn(b'value="urgent"', response.data)

    def test_valid_submissions_create_open_tickets_with_unique_ids(self):
        values = {
            "room": "  A101 ",
            "device": " Laptop ",
            "category": " Hardware ",
            "description": " Won't start ",
            "priority": "high",
        }

        first_response = self.client.post(
            "/tickets", data=values, follow_redirects=True
        )
        second_response = self.client.post(
            "/tickets", data=values, follow_redirects=True
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertIn(b"Ticket #1 (HD-000001) created successfully.", first_response.data)
        self.assertIn(b"Ticket #2 (HD-000002) created successfully.", second_response.data)
        self.assertIn(b"Status: Open.", first_response.data)

        with self.app.app_context():
            rows = get_db().execute(
                "SELECT * FROM tickets ORDER BY ticket_id"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["ticket_id"], rows[1]["ticket_id"])
        self.assertEqual(rows[0]["ticket_number"], "HD-000001")
        self.assertEqual(rows[0]["requester_id"], None)
        self.assertEqual(rows[0]["room"], "A101")
        self.assertEqual(rows[0]["device"], "Laptop")
        self.assertEqual(rows[0]["category"], "Hardware")
        self.assertEqual(rows[0]["description"], "Won't start")
        self.assertEqual(rows[0]["priority"], "high")
        self.assertEqual(rows[0]["status"], "open")
        self.assertEqual(rows[0]["created_at"], rows[0]["updated_at"])
        for timestamp in (rows[0]["created_at"], rows[0]["updated_at"]):
            self.assertTrue(timestamp.endswith("Z"))
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))

    def test_invalid_submissions_show_errors_preserve_values_and_save_nothing(self):
        valid_values = {
            "room": "A101",
            "device": "Laptop",
            "category": "Hardware",
            "description": "Will not start",
            "priority": "normal",
        }
        cases = (
            ({"room": None}, "room", "This field is required."),
            ({"room": "   "}, "room", "This field is required."),
            ({"device": ""}, "device", "This field is required."),
            ({"device": " \t "}, "device", "This field is required."),
            ({"category": "   "}, "category", "This field is required."),
            ({"category": ""}, "category", "This field is required."),
            ({"description": None}, "description", "This field is required."),
            ({"description": " \t "}, "description", "This field is required."),
            ({"priority": None}, "priority", "Select a valid priority."),
            ({"priority": ""}, "priority", "Select a valid priority."),
            ({"priority": "critical"}, "priority", "Select a valid priority."),
        )

        for changes, error_field, error_message in cases:
            with self.subTest(changes=changes):
                values = dict(valid_values)
                for field, value in changes.items():
                    if value is None:
                        values.pop(field)
                    else:
                        values[field] = value

                response = self.client.post("/tickets", data=values)

                self.assertEqual(response.status_code, 400)
                self.assertIn(error_message.encode(), response.data)
                self.assertIn(f'id="{error_field}-error"'.encode(), response.data)
                for field in ("room", "device", "category"):
                    submitted = values.get(field, "")
                    self.assertIn(
                        f'value="{submitted}"'.encode(),
                        response.data,
                    )
                if values.get("description"):
                    self.assertIn(values["description"].encode(), response.data)
                if values.get("priority") == "critical":
                    self.assertIn(b'value="critical" selected', response.data)
                with self.app.app_context():
                    count = get_db().execute(
                        "SELECT COUNT(*) FROM tickets"
                    ).fetchone()[0]
                self.assertEqual(count, 0)

    def test_database_write_failure_does_not_report_success_or_expose_details(self):
        values = {
            "room": "  A101 ",
            "device": "Laptop",
            "category": "Hardware",
            "description": "Will not start",
            "priority": "normal",
        }
        with self.app.app_context():
            get_db().execute(
                """
                CREATE TRIGGER reject_ticket_write
                BEFORE INSERT ON tickets
                BEGIN
                    SELECT RAISE(ABORT, 'sensitive SQL details');
                END
                """
            )
            get_db().commit()

        response = self.client.post("/tickets", data=values)

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"The ticket could not be saved. Please try again.", response.data)
        self.assertIn(b'value="  A101 "', response.data)
        self.assertNotIn(b"sensitive SQL details", response.data)
        self.assertNotIn(b"created successfully", response.data)
        with self.app.app_context():
            count = get_db().execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
