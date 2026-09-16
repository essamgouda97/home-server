"""Private server-side credential lookup. Never log returned values."""
import json
from pathlib import Path

def service_password(name):
    root=Path.home()/'.config/home-server/secrets'
    path=root/'service-passwords.json'
    values=json.loads(path.read_text()) if path.exists() else {}
    return values.get(name) or (root/'creative_password').read_text().strip()
