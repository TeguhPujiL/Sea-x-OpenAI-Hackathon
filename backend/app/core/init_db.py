"""Compatibility entrypoint for the explicit versioned SQLite migration."""
from app.core.migrations import main

if __name__ == "__main__":
    main()
