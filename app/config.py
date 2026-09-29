"""All settings come from environment variables.

Nothing environment-specific is hard-coded, so the same container image can run
locally, in CI and on Kubernetes. Kubernetes will inject these as env vars
(DATABASE_URL from a Secret, the rest from a ConfigMap).
"""
import os

# Local default is a SQLite file so the app runs with zero setup.
# In Docker/Kubernetes set e.g. postgresql+psycopg://user:pass@db:5432/uptime
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./uptime.db")

# How long to wait for a monitored site before calling it down.
CHECK_TIMEOUT_SECONDS = float(os.getenv("CHECK_TIMEOUT_SECONDS", "5"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
