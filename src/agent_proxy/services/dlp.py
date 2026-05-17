# services/dlp.py
import json
import re


class DLPService:
    def __init__(self):
        # In production, this should be a fast cache like Redis with an expiration/TTL
        # keyed by request_id, so memory doesn't leak over time.
        self._vault = {}

    def anonymize(self, request_id: str, payload_dict: dict) -> bytes:
        """
        Scans the payload, replaces sensitive data with tokens (e.g., [SECRET_1]),
        stores the mapping in the vault, and returns the newly encoded bytes.
        """
        payload_str = json.dumps(payload_dict)

        # Example: Naive AWS Key detection
        aws_keys = re.findall(r"(?<![A-Z0-9])[A-Z0-9]{20}(?![A-Z0-9])", payload_str)

        mapping = {}
        for i, key in enumerate(aws_keys):
            token = f"[REDACTED_AWS_{i}]"
            mapping[token] = key
            payload_str = payload_str.replace(key, token)

        # Store the mapping so we can reverse it later
        if mapping:
            self._vault[request_id] = mapping

        return payload_str.encode("utf-8")

    def deanonymize(self, request_id: str, response_text: str) -> str:
        """
        Takes the LLM's response, looks up the vault for this request,
        and injects the real data back in place of the tokens.
        """
        mapping = self._vault.get(request_id)
        if not mapping:
            return response_text  # Nothing to restore

        restored_text = response_text
        for token, real_value in mapping.items():
            restored_text = restored_text.replace(token, real_value)

        # Cleanup vault to prevent memory leaks
        del self._vault[request_id]

        return restored_text


dlp_service = DLPService()
