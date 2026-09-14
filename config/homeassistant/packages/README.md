# Versioned Home Assistant packages

Place YAML packages here. Runtime device credentials, users, pairing keys and
location data remain in the private `/config/.storage` directory outside Git.
Automations created in the UI remain in the writable `automations.yaml` file.
Export reusable logic as packages or blueprints after removing device identifiers
and secrets. Do not place example YAML here until it is valid for real devices.
