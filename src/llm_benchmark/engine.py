import uuid

from llm_benchmark.protocols import ModelClientProtocol, TelemetrySinkProtocol


class BenchmarkEngine:
    """
    Executes benchmark suites by bridging a Model Provider, an Evaluator, and a Telemetry Sink.
    """

    def __init__(self, client: ModelClientProtocol, sink: TelemetrySinkProtocol):
        self.client = client
        self.sink = sink

    async def run_suite(self, benchmark_data: list[dict[str, str]]) -> None:
        """Executes runs and evaluates them against ground truth."""

        for idx, item in enumerate(benchmark_data):
            prompt = item["prompt"]
            expected = item["expected"]
            run_id = f"bench-{uuid.uuid4()}"

            print(f"-> Running prompt {idx + 1}/{len(benchmark_data)} [{run_id}]...")

            try:
                result = await self.client.generate(run_id=run_id, prompt=prompt)

                # Enrich with ground truth and evaluate
                result.expected_output = expected
                result.is_correct = self._evaluate_correctness(
                    result.response_text, expected
                )

                print(
                    f"   TPS: {result.tokens_per_second} | Correct: {result.is_correct}"
                )

                await self.sink.flush(result)
            except Exception as exc:
                print(f"   [Error] Generation failed: {exc}")
                continue

        print("Benchmark suite complete.")

    def _evaluate_correctness(self, response: str, expected: str | None) -> bool:
        """
        A rudimentary lexical evaluator.
        Returns True if 50% or more of the words in the expected output exist in the response.
        """
        if not expected:
            return False

        expected_words = set(expected.lower().split())
        response_words = set(response.lower().split())

        if not expected_words:
            return False

        overlap = expected_words.intersection(response_words)
        match_ratio = len(overlap) / len(expected_words)

        return match_ratio >= 0.50
