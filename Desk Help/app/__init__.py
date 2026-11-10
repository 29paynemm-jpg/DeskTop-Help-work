import os
import sqlite3
from pathlib import Path

import click
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from .db import create_ticket
from .db import init_app as init_db_app
from .db import init_db

PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_FIELDS = ("room", "device", "category", "description", "priority")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.environ.get(
            "HELP_DESK_DATABASE",
            str(Path(app.instance_path) / "help_desk.sqlite"),
        ),
        SECRET_KEY=os.environ.get("HELP_DESK_SECRET_KEY") or os.urandom(32),
    )

    if test_config is not None:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_db_app(app)

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/tickets/new")
    def new_ticket():
        return render_template(
            "ticket_form.html",
            values={field: "" for field in TICKET_FIELDS},
            errors={},
            priorities=PRIORITIES,
        )

    @app.post("/tickets")
    def submit_ticket():
        values = {field: request.form.get(field, "") for field in TICKET_FIELDS}
        ticket_values = {
            field: value.strip() if field != "priority" else value
            for field, value in values.items()
        }
        errors = {}
        for field in ("room", "device", "category", "description"):
            if not ticket_values[field]:
                errors[field] = "This field is required."
        if ticket_values["priority"] not in PRIORITIES:
            errors["priority"] = "Select a valid priority."

        if errors:
            return (
                render_template(
                    "ticket_form.html",
                    values=values,
                    errors=errors,
                    priorities=PRIORITIES,
                ),
                400,
            )

        try:
            ticket_id = create_ticket(**ticket_values)
        except sqlite3.Error:
            app.logger.error("Unable to save ticket due to a database error.")
            return (
                render_template(
                    "ticket_form.html",
                    values=values,
                    errors={},
                    priorities=PRIORITIES,
                    form_error="The ticket could not be saved. Please try again.",
                ),
                503,
            )

        flash(
            f"Ticket #{ticket_id} (HD-{ticket_id:06d}) created successfully. "
            "Status: Open.",
            "success",
        )
        return redirect(url_for("new_ticket"))

    @app.cli.command("init-db")
    def init_db_command():
        """Create the database tables."""
        init_db()
        click.echo("Initialized the database.")

    return app
