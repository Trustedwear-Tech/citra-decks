"""
Image Generation Providers — abstraction layer over the image backends.

Three are supported, selected by ``IMAGE_GEN_PROVIDER``:

  runware   cloud, via the Runware SDK
  openai    any OpenAI-COMPATIBLE ``/images/generations`` endpoint — Together,
            Fal, DeepInfra, Nebius, or your own server. This is how you point
            citra-decks at a FLUX model without using Runware.
  comfyui   self-hosted ComfyUI server

All three return base64-encoded image data directly. The UI already handles
base64 via its ``image_data || image_url`` fallback.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import asyncio
import base64
import json
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)


# ─────────── Result dataclass ───────────

@dataclass
class ImageGenResult:
    """Unified result — always base64."""
    base64_data: str          # raw base64 string (no prefix)
    format: str = "PNG"       # PNG | JPG | WEBP

    @property
    def data_uri(self) -> str:
        mime = {
            "PNG": "image/png",
            "JPG": "image/jpeg",
            "JPEG": "image/jpeg",
            "WEBP": "image/webp",
        }.get(self.format.upper(), "image/png")
        return f"data:{mime};base64,{self.base64_data}"


# ─────────── Abstract provider ───────────

class ImageGenProvider(ABC):
    """Base class for image generation providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        model: str,
        timeout: int = 60,
    ) -> ImageGenResult:
        ...

    @abstractmethod
    async def edit(
        self,
        prompt: str,
        negative_prompt: str,
        source_image: str,
        width: int,
        height: int,
        model: str,
        strength: Optional[float] = None,
        timeout: int = 60,
    ) -> ImageGenResult:
        ...

    def supports_edit(self) -> bool:       # noqa: D102
        return False


# ─────────── Runware provider ───────────

class RunwareProvider(ImageGenProvider):
    """Cloud provider using the Runware Python SDK with base64 output."""

    def __init__(self) -> None:
        try:
            from runware import Runware, IImageInference
            from runware.types import IInputs
            self._Runware = Runware
            self._IImageInference = IImageInference
            self._IInputs = IInputs
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("⚠️ Runware SDK not installed — RunwareProvider unavailable")

    # ── helpers ──

    async def _call_sdk(self, kwargs: dict, timeout: int) -> ImageGenResult:
        if not self._available:
            raise RuntimeError("Runware SDK is not installed.")

        api_key = os.getenv("IMAGE_GEN_API_KEY", "").strip()
        if not api_key:
            raise ValueError("IMAGE_GEN_API_KEY not set.")

        sdk = self._Runware(api_key=api_key)
        try:
            await sdk.connect()
            request = self._IImageInference(**kwargs)
            images = await asyncio.wait_for(
                sdk.imageInference(requestImage=request),
                timeout=float(timeout),
            )
            if not images:
                raise ValueError("No images returned from Runware API.")

            img = images[0]
            # Prefer dataURI > base64Data > imageURL (fallback fetch)
            if img.imageDataURI:
                # dataURI is "data:image/png;base64,<data>"
                prefix, b64 = img.imageDataURI.split(",", 1)
                fmt = "PNG"
                if "jpeg" in prefix or "jpg" in prefix:
                    fmt = "JPG"
                elif "webp" in prefix:
                    fmt = "WEBP"
                return ImageGenResult(base64_data=b64, format=fmt)

            if img.imageBase64Data:
                return ImageGenResult(base64_data=img.imageBase64Data, format="PNG")

            # Fallback: SDK returned a URL — fetch it and base64-encode
            if img.imageURL:
                logger.info("⬇️ [RUNWARE] Falling back to URL fetch for base64 conversion")
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(img.imageURL)
                    resp.raise_for_status()
                    b64 = base64.b64encode(resp.content).decode()
                    ct = resp.headers.get("content-type", "image/png")
                    fmt = "JPG" if "jpeg" in ct or "jpg" in ct else "WEBP" if "webp" in ct else "PNG"
                    return ImageGenResult(base64_data=b64, format=fmt)

            raise ValueError("Runware response contained no image data.")
        except asyncio.TimeoutError:
            from image_gen_api import ImageGenTimeoutError
            model = kwargs.get("model", "unknown")
            raise ImageGenTimeoutError(
                f"Runware timed out after {timeout}s (model={model})"
            )
        finally:
            if hasattr(sdk, "disconnect"):
                await sdk.disconnect()

    # ── public API ──

    async def generate(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        model: str,
        timeout: int = 60,
    ) -> ImageGenResult:
        kwargs = dict(
            positivePrompt=prompt,
            negativePrompt=negative_prompt,
            model=model,
            width=width,
            height=height,
            numberResults=1,
            outputType="dataURI",
            outputFormat="PNG",
        )
        return await self._call_sdk(kwargs, timeout)

    async def edit(
        self,
        prompt: str,
        negative_prompt: str,
        source_image: str,
        width: int,
        height: int,
        model: str,
        strength: Optional[float] = None,
        timeout: int = 60,
    ) -> ImageGenResult:
        kwargs = dict(
            positivePrompt=prompt,
            negativePrompt=negative_prompt,
            model=model,
            width=width,
            height=height,
            numberResults=1,
            outputType="dataURI",
            outputFormat="PNG",
            inputs=self._IInputs(referenceImages=[source_image]),
        )
        return await self._call_sdk(kwargs, timeout)

    def supports_edit(self) -> bool:       # noqa: D102
        return True


# ─────────── OpenAI-compatible provider ───────────

class OpenAICompatProvider(ImageGenProvider):
    """Any endpoint exposing OpenAI's ``/images/generations`` shape.

    Lets you run FLUX (or anything else) through Together, Fal, DeepInfra,
    Nebius or your own server without a Runware account — configure it with
    the same three variables everything else in this repo uses:

        IMAGE_GEN_PROVIDER=openai
        IMAGE_GEN_BASE_URL=https://api.together.xyz/v1
        IMAGE_GEN_API_KEY=<key>
        IMAGE_GEN_MODEL=black-forest-labs/FLUX.1-dev

    Providers differ on how they hand the image back: some honour
    ``response_format="b64_json"``, others ignore it and return a URL
    regardless. Both are handled — a URL is fetched and encoded, so the
    caller always gets base64, matching the other providers.
    """

    def __init__(self) -> None:
        self.base_url = (os.getenv("IMAGE_GEN_BASE_URL") or "").strip()
        self.api_key = (os.getenv("IMAGE_GEN_API_KEY") or "").strip()
        if not self.base_url:
            raise ValueError(
                "IMAGE_GEN_PROVIDER=openai requires IMAGE_GEN_BASE_URL "
                "(e.g. https://api.together.xyz/v1)"
            )

    async def generate(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        model: str,
        timeout: int = 60,
    ) -> ImageGenResult:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "not-needed",
            timeout=float(timeout),
        )
        started = time.time()
        try:
            # negative_prompt has no place in the OpenAI image schema. Rather
            # than drop the caller's intent silently, append it as an explicit
            # instruction — the only way to carry it over this API shape.
            full_prompt = prompt
            if negative_prompt:
                full_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

            resp = await client.images.generate(
                model=model,
                prompt=full_prompt,
                size=f"{width}x{height}",
                response_format="b64_json",
                n=1,
            )
        except Exception as exc:                     # noqa: BLE001
            raise ValueError(f"Image generation failed via {self.base_url}: {exc}") from exc

        if not getattr(resp, "data", None):
            raise ValueError("Image endpoint returned no data.")
        item = resp.data[0]

        b64 = getattr(item, "b64_json", None)
        if b64:
            logger.info("🖼️ [OPENAI-IMG] generated in %.1fs", time.time() - started)
            return ImageGenResult(base64_data=b64, format="PNG")

        url = getattr(item, "url", None)
        if url:
            async with httpx.AsyncClient(timeout=timeout) as http:
                r = await http.get(url)
                r.raise_for_status()
                fmt = "PNG"
                ctype = (r.headers.get("content-type") or "").lower()
                if "jpeg" in ctype or "jpg" in ctype:
                    fmt = "JPG"
                elif "webp" in ctype:
                    fmt = "WEBP"
                logger.info("🖼️ [OPENAI-IMG] generated (via URL) in %.1fs", time.time() - started)
                return ImageGenResult(base64_data=base64.b64encode(r.content).decode(), format=fmt)

        raise ValueError("Image endpoint response contained neither b64_json nor url.")

    async def edit(
        self,
        prompt: str,
        negative_prompt: str,
        source_image: str,
        width: int,
        height: int,
        model: str,
        strength: Optional[float] = None,
        timeout: int = 60,
    ) -> ImageGenResult:
        # Deliberately unimplemented rather than faked. OpenAI's image EDIT
        # endpoint takes multipart image+mask and is not consistently offered
        # by the FLUX hosts this provider targets; supports_edit() returns
        # False so callers route around it instead of hitting a broken path.
        raise NotImplementedError(
            "Image editing is not available on the OpenAI-compatible provider. "
            "Use IMAGE_GEN_PROVIDER=runware for edits."
        )

    def supports_edit(self) -> bool:
        return False


# ─────────── ComfyUI provider ───────────

# Default polling settings
_COMFYUI_POLL_INTERVAL = 1.0   # seconds between /history polls
_COMFYUI_MAX_POLL = 120        # max seconds to wait for a generation


class ComfyUIProvider(ImageGenProvider):
    """On-prem provider — submits a workflow JSON to a ComfyUI server,
    polls /history for completion, and downloads the output image bytes."""

    def __init__(self) -> None:
        self._server_url = os.getenv(
            "COMFYUI_SERVER_URL", "http://localhost:8188"
        ).rstrip("/")
        self._workflows_dir = os.path.join(
            os.path.dirname(__file__), "workflows", "comfyui"
        )

    # ── helpers ──

    def _load_workflow(self, model: str) -> dict:
        """Load and return the workflow JSON template for the given model."""
        # Map model identifier → template filename
        model_lower = model.lower()
        if "schnell" in model_lower:
            template = "flux_schnell.json"
        elif "flux" in model_lower and "dev" in model_lower:
            template = "flux_dev.json"
        else:
            # Generic fallback — try using the model name as filename
            safe_name = model.replace("/", "_").replace(":", "_")
            template = f"{safe_name}.json"

        path = os.path.join(self._workflows_dir, template)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"No ComfyUI workflow template found for model '{model}' "
                f"(looked for {path})"
            )
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _parameterise_workflow(
        self,
        workflow: dict,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: Optional[int] = None,
    ) -> dict:
        """Substitute placeholders in a ComfyUI workflow template."""
        import random as _random

        raw = json.dumps(workflow)
        seed = seed if seed is not None else _random.randint(0, 2**32 - 1)
        raw = (
            raw.replace("{prompt}", prompt.replace('"', '\\"'))
            .replace("{negative_prompt}", negative_prompt.replace('"', '\\"'))
            .replace("{width}", str(width))
            .replace("{height}", str(height))
            .replace("{seed}", str(seed))
        )
        return json.loads(raw)

    async def _submit_and_wait(
        self, workflow: dict, timeout: int
    ) -> bytes:
        """POST workflow to ComfyUI /prompt, poll /history, download image bytes."""
        async with httpx.AsyncClient(
            base_url=self._server_url, timeout=30
        ) as client:
            # 1. Submit
            resp = await client.post("/prompt", json={"prompt": workflow})
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
            logger.info(f"🖼️ [COMFYUI] Submitted prompt_id={prompt_id}")

            # 2. Poll /history until done
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                hist_resp = await client.get(f"/history/{prompt_id}")
                hist_resp.raise_for_status()
                history = hist_resp.json()

                if prompt_id in history:
                    outputs = history[prompt_id].get("outputs", {})
                    # Find the first node that produced images
                    for _node_id, node_out in outputs.items():
                        images = node_out.get("images", [])
                        if images:
                            img_info = images[0]
                            filename = img_info["filename"]
                            subfolder = img_info.get("subfolder", "")
                            img_type = img_info.get("type", "output")
                            # 3. Download
                            params = {
                                "filename": filename,
                                "type": img_type,
                            }
                            if subfolder:
                                params["subfolder"] = subfolder
                            dl_resp = await client.get("/view", params=params)
                            dl_resp.raise_for_status()
                            logger.info(
                                f"✅ [COMFYUI] Downloaded {filename} "
                                f"({len(dl_resp.content)} bytes)"
                            )
                            return dl_resp.content

                    # If outputs exist but no images → generation error
                    status = history[prompt_id].get("status", {})
                    if status.get("status_str") == "error":
                        msgs = status.get("messages", [])
                        raise RuntimeError(
                            f"ComfyUI generation failed: {msgs}"
                        )

                await asyncio.sleep(_COMFYUI_POLL_INTERVAL)

            from image_gen_api import ImageGenTimeoutError
            raise ImageGenTimeoutError(
                f"ComfyUI generation timed out after {timeout}s "
                f"(prompt_id={prompt_id})"
            )

    # ── public API ──

    async def generate(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        model: str,
        timeout: int = 60,
    ) -> ImageGenResult:
        workflow = self._load_workflow(model)
        workflow = self._parameterise_workflow(
            workflow, prompt, negative_prompt, width, height
        )
        image_bytes = await self._submit_and_wait(workflow, timeout)
        b64 = base64.b64encode(image_bytes).decode()
        return ImageGenResult(base64_data=b64, format="PNG")

    async def edit(
        self,
        prompt: str,
        negative_prompt: str,
        source_image: str,
        width: int,
        height: int,
        model: str,
        strength: Optional[float] = None,
        timeout: int = 60,
    ) -> ImageGenResult:
        raise NotImplementedError(
            "Image editing is not yet supported for ComfyUI provider. "
            "Use the Runware provider for image editing."
        )

    def supports_edit(self) -> bool:       # noqa: D102
        return False

    async def health_check(self) -> bool:
        """Ping ComfyUI server to verify connectivity."""
        try:
            async with httpx.AsyncClient(
                base_url=self._server_url, timeout=5
            ) as client:
                resp = await client.get("/system_stats")
                resp.raise_for_status()
                logger.info(f"✅ [COMFYUI] Server reachable at {self._server_url}")
                return True
        except Exception as e:
            logger.error(
                f"❌ [COMFYUI] Server unreachable at {self._server_url}: {e}"
            )
            return False


# ─────────── Provider factory (singleton) ───────────

_provider_instance: Optional[ImageGenProvider] = None


def get_provider() -> ImageGenProvider:
    """Return the configured image generation provider (singleton)."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    provider_name = os.getenv("IMAGE_GEN_PROVIDER", "runware").strip().lower()

    if provider_name == "comfyui":
        _provider_instance = ComfyUIProvider()
        logger.info(
            f"🖼️ Image gen provider: ComfyUI "
            f"({os.getenv('COMFYUI_SERVER_URL', 'http://localhost:8188')})"
        )
    elif provider_name in ("openai", "openai-compat", "flux"):
        _provider_instance = OpenAICompatProvider()
        logger.info(
            f"🖼️ Image gen provider: OpenAI-compatible "
            f"({os.getenv('IMAGE_GEN_BASE_URL', '?')}, model "
            f"{os.getenv('IMAGE_GEN_MODEL', '?')})"
        )
    else:
        _provider_instance = RunwareProvider()
        logger.info("🖼️ Image gen provider: Runware (cloud)")

    return _provider_instance
