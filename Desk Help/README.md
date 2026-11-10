# School IT Help Desk

The project provides a Flask application foundation and SQLite schema. The current
ticket functionality is limited to creating a ticket; listing, authentication,
editing, assignment, and resolution workflows are out of scope.

## Setup

Use Python 3.9 or newer. From the project directory, create and activate a virtual
environment, then install the application dependency:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

By default, the database is created at `instance\help_desk.sqlite`. Set
`HELP_DESK_DATABASE` to use a different path. Initialize the schema with:

```powershell
flask --app app init-db
```

Run the test suite with:

```powershell
python -m unittest discover -s tests -v
```

The schema stores timestamps as UTC ISO-8601 text with a trailing `Z`.
Passwords are represented only by a `password_hash` column; password handling
and authentication are outside this phase.
Ticket creation is unauthenticated, so new tickets have no requester association
until a requester identity flow is introduced.

## Run the server

Start the Flask development server from the project directory:

```powershell
flask --app app run --debug
```

The home page is available at `http://127.0.0.1:5000/`, and the health check is
available at `http://127.0.0.1:5000/health`.
