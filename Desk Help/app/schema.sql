CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE CHECK (length(trim(username)) > 0),
    password_hash TEXT NOT NULL CHECK (length(trim(password_hash)) > 0),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    role TEXT NOT NULL CHECK (role IN ('requester', 'technician', 'admin')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id INTEGER PRIMARY KEY,
    ticket_number TEXT NOT NULL UNIQUE CHECK (length(trim(ticket_number)) > 0),
    requester_id INTEGER,
    room TEXT NOT NULL CHECK (length(trim(room)) > 0),
    device TEXT NOT NULL CHECK (length(trim(device)) > 0),
    category TEXT NOT NULL CHECK (length(trim(category)) > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    assigned_technician_id INTEGER,
    resolution_notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_at TEXT,
    CHECK (
        status <> 'resolved'
        OR (resolution_notes IS NOT NULL AND length(trim(resolution_notes)) > 0)
    ),
    FOREIGN KEY (requester_id) REFERENCES users (user_id),
    FOREIGN KEY (assigned_technician_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS ticket_events (
    event_id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    actor_id INTEGER,
    event_type TEXT NOT NULL CHECK (length(trim(event_type)) > 0),
    details TEXT NOT NULL CHECK (length(trim(details)) > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (ticket_id) REFERENCES tickets (ticket_id) ON DELETE CASCADE,
    FOREIGN KEY (actor_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_requester_id
    ON tickets (requester_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned_technician_id
    ON tickets (assigned_technician_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status
    ON tickets (status);
CREATE INDEX IF NOT EXISTS idx_tickets_priority
    ON tickets (priority);
CREATE INDEX IF NOT EXISTS idx_tickets_created_at
    ON tickets (created_at);
CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket_created_at
    ON ticket_events (ticket_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ticket_events_actor_id
    ON ticket_events (actor_id);
