import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.db import connect_db, get_db, init_db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = str(Path(self.temp_dir.name) / "test.sqlite")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
            }
        )
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.addCleanup(self.app_context.pop)

    def create_user(self, username="student"):
        cursor = get_db().execute(
            """
            INSERT INTO users (username, password_hash, display_name, role)
            VALUES (?, ?, ?, ?)
            """,
            (username, "test-hash", "Student User", "requester"),
        )
        return cursor.lastrowid

    def create_ticket(self, requester_id, **overrides):
        values = {
            "ticket_number": "HD-1001",
            "requester_id": requester_id,
            "room": "A101",
            "device": "Laptop",
            "category": "Hardware",
            "description": "Laptop will not start",
            "priority": "normal",
            "status": "open",
        }
        values.update(overrides)
        return get_db().execute(
            """
            INSERT INTO tickets (
                ticket_number, requester_id, room, device, category,
                description, priority, status, resolution_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["ticket_number"],
                values["requester_id"],
                values["room"],
                values["device"],
                values["category"],
                values["description"],
                values["priority"],
                values["status"],
                values.get("resolution_notes"),
            ),
        ).lastrowid

    def test_initialization_creates_tables_and_utc_timestamps(self):
        tables = {
            row["name"]
            for row in get_db().execute(
                "SELECT name FROM sqlite_master WHERE type = ?",
                ("table",),
            )
        }
        self.assertTrue({"users", "tickets", "ticket_events"} <= tables)

        user_id = self.create_user()
        row = get_db().execute(
            "SELECT created_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        self.assertRegex(row["created_at"], r"Z$")

    def test_initialization_can_be_run_repeatedly(self):
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)

        tables = {
            row["name"]
            for row in get_db().execute(
                "SELECT name FROM sqlite_master WHERE type = ?",
                ("table",),
            )
        }
        self.assertTrue({"users", "tickets", "ticket_events"} <= tables)

    def test_initialization_migrates_existing_required_requester_schema(self):
        legacy_path = str(Path(self.temp_dir.name) / "legacy.sqlite")
        legacy_app = create_app(
            {
                "TESTING": True,
                "DATABASE": legacy_path,
            }
        )
        with legacy_app.open_resource("schema.sql") as schema_file:
            legacy_schema = schema_file.read().decode("utf-8").replace(
                "requester_id INTEGER,",
                "requester_id INTEGER NOT NULL,",
                1,
            )
        connection = connect_db(legacy_path)
        try:
            connection.executescript(legacy_schema)
            connection.execute(
                """
                INSERT INTO users (username, password_hash, display_name, role)
                VALUES (?, ?, ?, ?)
                """,
                ("legacy-student", "hash", "Legacy Student", "requester"),
            )
            connection.execute(
                """
                INSERT INTO tickets (
                    ticket_number, requester_id, room, device, category,
                    description, priority
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("HD-LEGACY", 1, "A101", "Laptop", "Hardware", "Broken", "low"),
            )
            connection.execute(
                """
                INSERT INTO ticket_events (ticket_id, event_type, details)
                VALUES (?, ?, ?)
                """,
                (1, "created", "Legacy ticket"),
            )
            connection.commit()
        finally:
            connection.close()

        with legacy_app.app_context():
            init_db()

        migrated = connect_db(legacy_path)
        try:
            requester_column = next(
                row
                for row in migrated.execute("PRAGMA table_info(tickets)")
                if row["name"] == "requester_id"
            )
            self.assertEqual(requester_column["notnull"], 0)
            self.assertEqual(
                migrated.execute(
                    "SELECT ticket_number FROM tickets WHERE ticket_id = 1"
                ).fetchone()["ticket_number"],
                "HD-LEGACY",
            )
            self.assertEqual(
                migrated.execute("SELECT COUNT(*) FROM ticket_events").fetchone()[0],
                1,
            )
            self.assertEqual(
                migrated.execute("PRAGMA foreign_key_check").fetchall(),
                [],
            )
        finally:
            migrated.close()

    def test_foreign_keys_are_enabled_on_each_connection(self):
        first_connection = connect_db(self.database_path)
        second_connection = connect_db(self.database_path)
        try:
            self.assertEqual(
                first_connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
            )
            self.assertEqual(
                second_connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
            )

            with self.assertRaises(sqlite3.IntegrityError):
                first_connection.execute(
                    """
                    INSERT INTO tickets (
                        ticket_number, requester_id, room, device, category,
                        description, priority
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("HD-404", 987654, "A101", "Laptop", "Hardware", "Broken", "low"),
                )

            with self.assertRaises(sqlite3.IntegrityError):
                first_connection.execute(
                    """
                    INSERT INTO ticket_events (ticket_id, event_type, details)
                    VALUES (?, ?, ?)
                    """,
                    (987654, "created", "Ticket created"),
                )
        finally:
            first_connection.close()
            second_connection.close()

    def test_checks_unique_values_and_valid_enums(self):
        user_id = self.create_user()
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_user()

        with self.assertRaises(sqlite3.IntegrityError):
            self.create_ticket(user_id, ticket_number="  ")
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_ticket(user_id, ticket_number="HD-1002", priority="critical")
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_ticket(user_id, ticket_number="HD-1003", status="pending")

        self.create_ticket(user_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_ticket(user_id, ticket_number="HD-1001")

    def test_resolved_ticket_requires_nonblank_resolution_notes(self):
        user_id = self.create_user()
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_ticket(user_id, status="resolved")
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_ticket(
                user_id,
                status="resolved",
                resolution_notes="   ",
            )

        self.create_ticket(
            user_id,
            status="resolved",
            resolution_notes="Replaced the charger.",
        )

    def test_expected_indexes_exist(self):
        index_names = {
            row["name"]
            for row in get_db().execute(
                "SELECT name FROM sqlite_master WHERE type = ?",
                ("index",),
            )
        }
        self.assertTrue(
            {
                "idx_tickets_requester_id",
                "idx_tickets_assigned_technician_id",
                "idx_tickets_status",
                "idx_tickets_priority",
                "idx_tickets_created_at",
                "idx_ticket_events_ticket_created_at",
                "idx_ticket_events_actor_id",
            } <= index_names
        )


if __name__ == "__main__":
    unittest.main()
