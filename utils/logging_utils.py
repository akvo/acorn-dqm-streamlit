import json
import logging
import sys
from datetime import datetime


class JSONAuditFormatter(logging.Formatter):
    """
    A custom logging formatter that outputs log records as single-line JSON.
    It redacts sensitive credentials/keys and masks usernames to prevent PII exposure.
    """

    SENSITIVE_KEYS = {"password", "auth", "token", "secret", "key", "api_key", "credentials"}

    def mask_username(self, username) -> str:
        if not username:
            return "(empty)"
        username_str = str(username).strip()
        if len(username_str) < 3:
            return "***"
        return f"{username_str[:3]}***"

    def redact_value(self, value):
        if isinstance(value, dict):
            return self.redact_dict(value)
        elif isinstance(value, list):
            return [self.redact_value(item) for item in value]
        elif isinstance(value, str):
            return self.redact_string(value)
        return value

    def redact_dict(self, d: dict) -> dict:
        redacted = {}
        for k, v in d.items():
            key_lower = str(k).lower()
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_KEYS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = self.redact_value(v)
        return redacted

    def redact_string(self, s: str) -> str:
        # If the string itself contains raw Authorization header, redact it
        if "bearer " in s.lower() or "basic " in s.lower():
            return "[REDACTED]"

        # Check if the string is serialized JSON
        try:
            parsed = json.loads(s)
            if isinstance(parsed, (dict, list)):
                redacted = self.redact_value(parsed)
                return json.dumps(redacted)
        except (ValueError, TypeError):
            pass

        return s

    def format(self, record: logging.LogRecord) -> str:
        # Create standard log metadata fields
        log_data = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Parse extra parameters on the log record
        # Filter out built-in LogRecord attributes to capture only "extra" keyword arguments
        builtin_attrs = {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
        }

        for key, value in record.__dict__.items():
            if key not in builtin_attrs:
                # Apply username masking if it is the username key
                if key.lower() == "username":
                    log_data[key] = self.mask_username(value)
                elif key.lower() in self.SENSITIVE_KEYS or any(
                    sensitive in key.lower() for sensitive in self.SENSITIVE_KEYS
                ):
                    log_data[key] = "[REDACTED]"
                else:
                    if isinstance(value, str):
                        sanitized = self.redact_string(value)
                        # Cap extremely long response bodies
                        if len(sanitized) > 200:
                            log_data[key] = sanitized[:200] + "..."
                        else:
                            log_data[key] = sanitized
                    else:
                        log_data[key] = self.redact_value(value)

        # Ensure serialization doesn't throw a TypeError on custom objects
        try:
            return json.dumps(log_data)
        except TypeError:
            # Fallback serialization
            serializable_log_data = {}
            for k, v in log_data.items():
                try:
                    json.dumps({k: v})
                    serializable_log_data[k] = v
                except TypeError:
                    serializable_log_data[k] = str(v)
            return json.dumps(serializable_log_data)


def get_audit_logger(name: str = "audit", stream=None) -> logging.Logger:
    """
    Returns a configured audit logger that outputs only JSON format messages.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        handler = logging.StreamHandler(stream or sys.stdout)
        formatter = JSONAuditFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False  # Prevent logs propagating to root Streamlit logger

    return logger
