import os

# Safe defaults so unit tests never need real services or secrets.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("GEMINI_API_KEY", "")
