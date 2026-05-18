from typing import Any


def _extract_latest_user_prompt(request_body: any) -> str | None:
    """Extracts the specific user task, stripping away agent system boilerplate."""
    if not isinstance(request_body, dict):
        return None

    messages = request_body.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return None

    # Find the last message from the user
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if not content:
                continue

            # Handle Vision-style list content
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )

            content_str = str(content).strip()

            # --- OPENCODE SPECIFIC CLEANING ---
            # In your example, the real prompt follows the 'No skills are currently available.' marker.
            marker = "No skills are currently available.,"
            if marker in content_str:
                # Split and take the part after the marker
                parts = content_str.split(marker)
                # The last part contains the prompt, usually wrapped in quotes or commas
                raw_prompt = parts[-1].strip()
                # Clean up trailing artifacts like leading/trailing quotes or commas
                return raw_prompt.strip(" '\",")

            # --- GENERAL FALLBACK ---
            # If the string is massive (boilerplate present) but marker not found,
            # we might just want the last 500 characters as a summary.
            if len(content_str) > 1000:
                return content_str[-500:] + "..."

            return content_str

    return None


def _extract_last_message(request_body: any) -> str | None:
    """Extracts a summary of the very last message in the conversation array."""
    if not isinstance(request_body, dict):
        return None

    messages = request_body.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return None

    last = messages[-1]
    role = last.get("role", "unknown").upper()
    content = last.get("content", "")

    # Handle Assistant messages that have no text content but do have reasoning or tool calls
    if not content:
        if last.get("reasoning_content"):
            content = f"[Reasoning] {last['reasoning_content']}"
        elif last.get("tool_calls"):
            t_names = [tc.get("function", {}).get("name") for tc in last["tool_calls"]]
            content = f"[Tool Calls] {', '.join(filter(None, t_names))}"

    # Handle Tool messages (like the file content in your log)
    # We truncate to 1000 chars so ES doesn't choke on huge file reads
    summary = str(content).strip()
    return f"{role}: {summary[:1000]}{'...' if len(summary) > 1000 else ''}"


def _extract_usage(response_body: Any) -> dict | None:
    """Safely extracts usage stats from a parsed response body."""
    # TODO: Move some of these into the parser utility module
    if not response_body:
        return None

    # Standard JSON response
    if isinstance(response_body, dict):
        return response_body.get("usage")

    # SSE Stream (if your parse_body returns a list of chunks)
    if isinstance(response_body, list):
        for chunk in reversed(response_body):
            if isinstance(chunk, dict) and chunk.get("usage"):
                return chunk.get("usage")

    return None
