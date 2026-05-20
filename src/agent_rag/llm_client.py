import httpx


class OpenRouterClient:
    """Handles inference via OpenRouter API and extracts token usage."""

    def __init__(self, api_key: str, model: str = "moonshotai/kimi-k2.5"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"

    async def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        """Returns the generated text and the token usage dictionary."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

            answer = data["choices"][0]["message"]["content"]
            usage = data.get(
                "usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            )

            return answer, usage
