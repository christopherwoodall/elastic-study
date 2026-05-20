import asyncio
import time

import torch
from peft import PeftModel
from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

from llm_benchmark.protocols import TelemetryResult


class NemotronDiffusionClient:
    """
    A specialized client for nvidia/Nemotron-Labs-Diffusion-8B.
    Implements 4-bit quantization to fit on an RTX 3080 and handles
    custom speculative decoding generation.
    """

    def __init__(self, repo_name: str = "nvidia/Nemotron-Labs-Diffusion-8B"):
        self.repo_name = repo_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.tokenizer = None

    async def load_model(self) -> None:
        print(f"Hardware Check: {self.device.upper()}")
        if self.device != "cuda":
            raise RuntimeError("CUDA is required for Nemotron-Diffusion.")

        print(f"Downloading and loading '{self.repo_name}' in 4-bit precision...")
        await asyncio.to_thread(self._sync_load)
        print("Nemotron successfully loaded into VRAM.")

    def _sync_load(self) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.repo_name, trust_remote_code=True
        )

        # 1. 4-bit Quantization is mandatory for the RTX 3080
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        # 2. Load the base model using AutoModel (not AutoModelForCausalLM)
        base_model = AutoModel.from_pretrained(
            self.repo_name,
            trust_remote_code=True,
            quantization_config=quantization_config,
            device_map="auto",
        )

        # 3. Attach the linear_spec LoRA adapter and unwrap as per Nvidia's docs
        peft_model = PeftModel.from_pretrained(
            base_model, self.repo_name, subfolder="linear_spec_lora"
        ).eval()

        self.model = peft_model.model

    async def generate(self, run_id: str, prompt: str) -> TelemetryResult:
        history = [{"role": "user", "content": prompt}]
        formatted_prompt = self.tokenizer.apply_chat_template(
            history, tokenize=False, add_generation_prompt=True
        )
        prompt_ids = self.tokenizer(
            formatted_prompt, return_tensors="pt"
        ).input_ids.cuda()

        start_time = time.perf_counter()

        def _generate():
            return self.model.linear_spec_generate(
                prompt_ids,
                max_new_tokens=256,
                block_length=32,
                eos_token_id=self.tokenizer.eos_token_id,
            )

        out_ids, nfe = await asyncio.to_thread(_generate)
        end_time = time.perf_counter()

        # Slice to get new tokens and decode to text
        new_token_ids = out_ids[0, prompt_ids.shape[1] :]
        output_tokens = len(new_token_ids)
        response_text = self.tokenizer.decode(
            new_token_ids, skip_special_tokens=True
        ).strip()

        total_time_ms = (end_time - start_time) * 1000
        tps = (
            output_tokens / (end_time - start_time)
            if (end_time - start_time) > 0
            else 0.0
        )

        return TelemetryResult(
            run_id=run_id,
            model_name=f"{self.repo_name}-LinearSpec",
            prompt=prompt,
            response_text=response_text,
            expected_output=None,  # Engine will hydrate this
            is_correct=None,  # Engine will evaluate this
            time_to_first_token_ms=round(total_time_ms, 2),
            tokens_per_second=round(tps, 2),
            total_latency_ms=round(total_time_ms, 2),
            output_tokens=output_tokens,
        )

    async def close(self) -> None:
        if self.model:
            del self.model
            torch.cuda.empty_cache()
