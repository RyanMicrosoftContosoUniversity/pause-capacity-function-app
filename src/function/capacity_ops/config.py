"""Environment-backed configuration.

Read once at import, which is also when the Functions host indexes the app.

Other modules must reach these through the module (``config.RESOURCE_GROUP``)
rather than importing the names directly. ``from .config import RESOURCE_GROUP``
binds a copy at import time, which silently defeats both monkeypatching in tests
and any future support for re-reading settings.
"""

import os

RESOURCE_GROUP = os.getenv("FABRIC_RESOURCE_GROUP", "fabric-rg")

# How long to wait for a resumed capacity to report Active.
RESUME_POLL_TIMEOUT_SECONDS = int(os.getenv("RESUME_POLL_TIMEOUT_SECONDS", "900"))
RESUME_POLL_INTERVAL_SECONDS = int(os.getenv("RESUME_POLL_INTERVAL_SECONDS", "20"))

# Optional: workspace to health-check after resume.
HEALTHCHECK_WORKSPACE_ID = os.getenv("HEALTHCHECK_WORKSPACE_ID", "")
HEALTHCHECK_TIMEOUT_SECONDS = int(os.getenv("HEALTHCHECK_TIMEOUT_SECONDS", "600"))
HEALTHCHECK_INTERVAL_SECONDS = int(os.getenv("HEALTHCHECK_INTERVAL_SECONDS", "30"))


def subscription_id():
    """Read at call time, matching the original behaviour."""
    return os.getenv("SUBSCRIPTION_ID")
