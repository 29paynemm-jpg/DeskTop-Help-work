from datetime import datetime, timezone
import sqlite3

from flask import current_app, g


def connect_db(database_path):
    """Open a SQLite connection with foreign-key checks enabled."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db():
    if "db" not in g:
        g.db = connect_db(current_app.config["DATABASE"])
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db():
    connection = connect_db(current_app.config["DATABASE"])
    try:
        with current_app.open_resource("schema.sql") as schema_file:
            schema = schema_file.read().decode("utf-8")
        connection.executescript(schema)
        _migrate_nullable_requester(connection)
        connection.executescript(schema)
    finally:
        connection.close()


def create_ticket(*, room, device, category, description, priority):
    connection = get_db()
    try:
        connection.execute("BEGIN IMMEDIATE")
        next_id = connection.execute(
            "SELECT COALESCE(MAX(ticket_id), 0) + 1 FROM tickets"
        ).fetchone()[0]
        while connection.execute(
            "SELECT 1 FROM tickets WHERE ticket_number = ?",
            (f"HD-{next_id:06d}",),
        ).fetchone():
            next_id += 1
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, ticket_number, requester_id, room, device, category,
                description, priority, status, created_at, updated_at
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                next_id,
                f"HD-{next_id:06d}",
                room,
                device,
                category,
                description,
                priority,
                now,
                now,
            ),
        )
        connection.commit()
        return next_id
    except Exception:
        connection.rollback()
        raise


def _migrate_nullable_requester(connection):
    requester_column = next(
        (
            row
            for row in connection.execute("PRAGMA table_info(tickets)")
            if row["name"] == "requester_id"
        ),
        None,
    )
    if requester_column is None or requester_column["notnull"] == 0:
        return

    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE tickets_without_required_requester (
                ticket_id INTEGER PRIMARY KEY,
                ticket_number TEXT NOT NULL UNIQUE
                    CHECK (length(trim(ticket_number)) > 0),
                requester_id INTEGER,
                room TEXT NOT NULL CHECK (length(trim(room)) > 0),
                device TEXT NOT NULL CHECK (length(trim(device)) > 0),
                category TEXT NOT NULL CHECK (length(trim(category)) > 0),
                description TEXT NOT NULL CHECK (length(trim(description)) > 0),
                priority TEXT NOT NULL
                    CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
                assigned_technician_id INTEGER,
                resolution_notes TEXT,
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                resolved_at TEXT,
                CHECK (
                    status <> 'resolved'
                    OR (
                        resolution_notes IS NOT NULL
                        AND length(trim(resolution_notes)) > 0
                    )
                ),
                FOREIGN KEY (requester_id) REFERENCES users (user_id),
                FOREIGN KEY (assigned_technician_id) REFERENCES users (user_id)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO tickets_without_required_requester (
                ticket_id, ticket_number, requester_id, room, device, category,
                description, priority, status, assigned_technician_id,
                resolution_notes, created_at, updated_at, resolved_at
            )
            SELECT
                ticket_id, ticket_number, requester_id, room, device, category,
                description, priority, status, assigned_technician_id,
                resolution_notes, created_at, updated_at, resolved_at
            FROM tickets
            """
        )
        connection.execute("DROP TABLE tickets")
        connection.execute(
            "ALTER TABLE tickets_without_required_requester RENAME TO tickets"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def init_app(app):
    app.teardown_appcontext(close_db)
