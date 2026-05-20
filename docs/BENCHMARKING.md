# LLM Benchmarking Suite

A hardware-native, decoupled benchmarking suite for Large Language Models.
Executes Hugging Face models directly on your local GPU and ships performance telemetry (Throughput, Latency, TTFT) alongside correctness evaluations to a composite sink (Local JSONL + Elasticsearch) — without polluting your proxy's operational logs.

## Getting Started

**Step 1.** Install Machine Learning dependencies

Because this suite runs models natively on your GPU (bypassing external APIs), it requires standard deep learning libraries, including tools for 4-bit quantization to fit 8B+ parameter models on an RTX 3080.

```bash
uv pip install torch transformers accelerate bitsandbytes peft httpx
```

**Step 2.** Configure environment

Update your `.env` file to target the model you wish to benchmark. The suite automatically inherits your existing Elasticsearch configuration.

```env
TARGET_MODEL=nvidia/Nemotron-Labs-Diffusion-8B
ELASTIC_URL=http://localhost:9200
ELASTIC_INDEX=llm-proxy-logs
```

**Step 3.** Run the benchmark

The engine will check your hardware, download the specified model into VRAM, fetch real-world prompts (and expected answers) from the Hugging Face Alpaca dataset, and begin the benchmark loop.

```bash
uv run --env-file .env benchmark-run
```

**Step 4.** View local logs or hydrate Elasticsearch

By default, logs are written immediately to `./logs/benchmarks/run_<timestamp>.jsonl` and simultaneously pushed to Elasticsearch.

If Elasticsearch was unreachable during your run, or you ran the benchmark offline, you can hydrate the database using the local files:

```bash
uv run --env-file .env benchmark-hydrate
```

---

## Configuration

All settings are controlled via environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `TARGET_MODEL` | `nvidia/Nemotron-Labs-Diffusion-8B` | The Hugging Face repo ID to download and evaluate. |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch node URL. |
| `ELASTIC_INDEX` | `llm-proxy-logs` | Base index. Benchmarks are appended with `-benchmarks` (e.g., `llm-proxy-logs-benchmarks`). |

---

## Architecture

```text
                      ┌─────────────────────────┐
                      │   HF Datasets Server    │
                      └───────────┬─────────────┘
                                  │ (Alpaca Prompts + Answers)
                                  ▼
┌─────────────────┐    ┌─────────────────────────┐    ┌─────────────────┐
│ Local GPU (3080)│◄───┤  Benchmark Engine       ├───►│ Composite Sink  │
│ (4-bit Weights) │───►│  (+ Lexical Evaluator)  │    │ (Broadcaster)   │
└─────────────────┘    └─────────────────────────┘    └────────┬────────┘
                                                               │
                                                         ┌─────┴─────┐
                                                         ▼           ▼
                                              ┌────────────┐    ┌─────────────┐
                                              │Local .jsonl│    │Elasticsearch│
                                              │./logs      │    │:9200        │
                                              └────────────┘    └─────────────┘

```

### Features

* **Decoupled Architecture:** Strictly adheres to the Dependency Inversion Principle using Python Protocols, ensuring the benchmarking logic remains entirely isolated from the main proxy application.
* **Hardware-Aware Loading:** Automatically provisions 4-bit quantization (via `bitsandbytes`) for models that exceed standard consumer VRAM limits.
* **Realistic Testing & Evaluation:** Rather than using static test strings, the engine dynamically downloads instructions and ground-truth outputs from Hugging Face datasets (e.g., Stanford Alpaca) to simulate real-world context lengths.
* **Automated Scoring:** Features a lightweight lexical overlap evaluator that checks if the generated response accurately reflects the expected dataset output.
* **Resilient Logging:** Dual-sink output ensures no telemetry is lost if the Elasticsearch cluster is unavailable during a long hardware test.

---

## Log Schema

Each document pushed to the local JSONL files and the `<ELASTIC_INDEX>-benchmarks` index has the following shape:

```json
{
  "run_id": "bench-550e8400-e29b-41d4-a716-446655440000",
  "model_name": "nvidia/Nemotron-Labs-Diffusion-8B-LinearSpec",
  "prompt": "List the fundamental principles of physics...",
  "response_text": "The fundamental principles of physics include Newton's laws...",
  "expected_output": "Newton's laws of motion, thermodynamics, relativity...",
  "is_correct": true,
  "time_to_first_token_ms": 3450.21,
  "tokens_per_second": 24.5,
  "total_latency_ms": 13905.82,
  "output_tokens": 256
}
```

### Notes on Telemetry & Evaluation

* **Speculative Decoding (Nemotron):** Models that utilize custom generation loops (like `linear_spec_generate` or batch processing) process multiple tokens simultaneously. In these cases, precise Time-to-First-Token (TTFT) streaming cannot be intercepted natively. TTFT will reflect the total latency, but `tokens_per_second` (TPS) remains highly accurate as a measure of overall throughput.
* **Lexical Evaluation:** The `is_correct` field is generated by a heuristic evaluator that checks for a ≥50% vocabulary overlap between the `expected_output` and the `response_text`. This provides directional accuracy metrics without requiring a secondary LLM-as-a-judge.
* **Hydration:** Running `uv run hydrate-benchmarks` is idempotent for your file system; it reads all files in `./logs/benchmarks` but does not delete them. Ensure you rotate or clear your logs manually if you do not want to re-ingest old data upon subsequent hydration runs.
