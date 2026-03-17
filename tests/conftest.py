import os

# Ensure test env vars are set before any imports touch settings
os.environ.setdefault("AVIASALES_API_TOKEN", "test-token-for-testing")
os.environ.setdefault("AVIASALES_PARTNER_ID", "12345")
