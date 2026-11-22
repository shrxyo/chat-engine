import os

# Imported before conftest (and so before app.main builds its app). Tests must
# never export traces, even when the developer's .env enables them (S7.2).
# Environment variables take precedence over .env in pydantic-settings.
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
