"""
Image Generation API - Image generation module for the Citra AI Service.
Supports cloud and self-hosted image generation endpoints.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
import logging
import os
import json
import asyncio
import random
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, retry_if_not_exception_type

import base64
import httpx

from image_gen_providers import get_provider, ImageGenResult


def _compress_data_uri(data_uri: str) -> str:
    """Re-encode a generated image data URI to compressed JPEG (or optimized PNG
    when it has transparency). Providers (e.g. Runware) can return effectively
    uncompressed images — ~4.1MB base64 for 1152×896 — which then live in the
    deck state and get uploaded to S3 verbatim on save. Compressing at the
    generation source shrinks everything downstream ~10× without touching the
    upload-on-save lifecycle. On any error, log loudly and return the original
    (a big image is better than no image)."""
    try:
        if not data_uri or not data_uri.startswith("data:image"):
            return data_uri
        import io
        from PIL import Image
        _header, b64 = data_uri.split(",", 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        buf = io.BytesIO()
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        if has_alpha:
            img.save(buf, format="PNG", optimize=True)
            mime = "image/png"
        else:
            img.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
            mime = "image/jpeg"
        out = base64.b64encode(buf.getvalue()).decode()
        if len(out) < len(b64):
            logger.info(f"🗜️ [IMAGE_GEN] Compressed {len(b64):,} → {len(out):,} b64 chars ({mime})")
            return f"data:{mime};base64,{out}"
        return data_uri
    except Exception as e:
        logger.error(f"🗜️ [IMAGE_GEN] Compression failed — returning original image: {e}")
        return data_uri


def _compute_aspect_ratio(width: int, height: int) -> str:
    """
    Compute the closest supported aspect ratio from width/height.
    Supported: 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 2:1, 1:2, auto
    """
    if not width or not height:
        return "auto"
    ratio = width / height
    candidates = [
        (1.0, "1:1"), (16/9, "16:9"), (9/16, "9:16"),
        (4/3, "4:3"), (3/4, "3:4"), (3/2, "3:2"),
        (2/3, "2:3"), (2/1, "2:1"), (1/2, "1:2"),
    ]
    best = min(candidates, key=lambda c: abs(ratio - c[0]))
    return best[1]

# Initialize logger
logger = logging.getLogger(__name__)


class ImageGenTimeoutError(Exception):
    """Custom exception for image generation API timeouts. NOT retried by tenacity."""
    pass

# Import credit check middleware if available
try:
    from middleware.credit_check_middleware import track_query_usage, check_user_credits, get_usage_service
    BILLING_AVAILABLE = True
except ImportError:
    # Fallback/mock for standalone testing
    BILLING_AVAILABLE = False
    def track_query_usage(*args, **kwargs): pass
    def check_user_credits(*args, **kwargs): return {'success': True}
    def get_usage_service(): return None
    logger.warning("⚠️ Credit tracking not available for image generation")

from citra_auth import get_secure_user_id

router = APIRouter()

# ==================== Model Token-Consumption Defaults ====================
# Hardcoded fallback token-consumption per image, used when DB pricing is missing a model entry.
# This ensures usage is still recorded even before pricing_configs in MongoDB is updated.
MODEL_TOKEN_DEFAULTS: dict[str, float] = {


}
DEFAULT_IMAGE_TOKENS = 1.0     # token-consumption units per image if model is completely unknown

# Single model for all image operations (generation + editing)

EDIT_CAPABLE_MODEL = os.getenv("IMAGE_GEN_MODEL", "runware:400@1")

# ==================== Request/Response Models ====================

class ImageGenRequest(BaseModel):
    prompt: str = Field(..., description="Image generation prompt")
    width: Optional[int] = Field(default=1024, description="Image width (default 1024)")
    height: Optional[int] = Field(default=1024, description="Image height (default 1024)")
    model: Optional[str] = Field(default=None, description="Model ID")

    @field_validator('width', 'height', mode='before')
    @classmethod
    def coerce_float_to_int(cls, v):
        """Accept float dimensions (e.g. 333.6) and round to nearest int."""
        if isinstance(v, float):
            return round(v)
        return v

class ImageGenEditRequest(BaseModel):
    prompt: str = Field(..., description="Edit instruction prompt")
    source_image: str = Field(..., description="Source image URL or base64 data to edit")
    width: Optional[int] = Field(default=1024, description="Image width")
    height: Optional[int] = Field(default=1024, description="Image height")
    model: Optional[str] = Field(default=None, description="Model ID")
    strength: Optional[float] = Field(default=None, description="Edit strength 0-1 (lower = closer to original).")
    image_type: Optional[str] = Field(default="photo", description="Image type: photo | infographic | photo_with_text")

    @field_validator('width', 'height', mode='before')
    @classmethod
    def coerce_float_to_int(cls, v):
        if isinstance(v, float):
            return round(v)
        return v

class ImageGenResponse(BaseModel):
    success: bool
    image_url: Optional[str] = Field(default=None, description="URL of the generated image")
    image_data: Optional[str] = Field(default=None, description="Base64 encoded image data")
    message: Optional[str] = Field(default=None, description="Error or status message")


# ==================== Helper Functions ====================

def _get_image_gen_token_cost(model: str = None) -> float:
    """
    Get image generation token-consumption units dynamically from pricing configuration.
    Looks up 'image_generation' key first, uses the image_generation tier.
    Default: 1.0 token-consumption units per image if no DB config found.
    """
    try:
        if BILLING_AVAILABLE:
            usage_service = get_usage_service()
            if usage_service:
                pricing = usage_service.get_pricing()
                
                if pricing:
                    token_pricing = pricing.get('token_pricing', {})
                    # Try new generic key first, look up image_generation pricing
                    image_pricing = token_pricing.get('image_generation', {})
                    
                    # Direct lookup for model-specific pricing
                    price_obj = image_pricing.get(model)
                    
                    if not price_obj:
                         price_obj = image_pricing.get('default')

                    if price_obj and isinstance(price_obj, dict):
                         image_price = price_obj.get('image_generation_price')
                         if image_price is not None:
                              image_price = float(image_price)
                              logger.debug(f"💠 [USAGE] Found image gen token-cost for '{model}': {image_price:.2f} units")
                              return image_price

                    # Fallback to flat structure (legacy)
                    if isinstance(image_pricing, dict) and 'image_generation_price' in image_pricing:
                         image_price = image_pricing.get('image_generation_price')
                         if image_price is not None:
                              return float(image_price)

    except Exception as e:
        logger.error(f"❌ [PRICING] Error accessing cached image gen pricing: {e}")

    # Fallback to hardcoded defaults — 1.0 token-consumption units per image
    fallback_tokens = MODEL_TOKEN_DEFAULTS.get(model, DEFAULT_IMAGE_TOKENS)
    logger.warning(f"⚠️ [USAGE] No DB config found for '{model}', using fallback {fallback_tokens} units")
    return fallback_tokens

def _get_target_dimensions(width: Optional[int], height: Optional[int]) -> tuple[int, int]:
    """
    Map requested (width, height) to standard SDXL dimension presets (~1MP).
    Used ONLY for SDXL-based models that require standard dimensions.
    NOT for Google models — use _get_nano_banana_v25_dimensions / _get_nano_banana_v3_dimensions instead.

    Supported sizes:
      Landscape : 1152×896 (~5:4, 1.29), 1184×864 (~4:3, 1.37), 1248×832 (3:2, 1.50),
                  1344×768 (~16:9, 1.75), 1536×672 (~21:9, 2.29)
      Square    : 1024×1024 (1:1)
      Portrait  : 896×1152 (~4:5, 0.78), 864×1184 (~3:4, 0.73), 832×1248 (2:3, 0.67),
                  768×1344 (~9:16, 0.57)

    Midpoint boundaries:
      Landscape: 1.05 | 1.33 | 1.44 | 1.63 | 2.02
      Portrait:  0.95 | 0.75 | 0.70 | 0.62
    """
    if not width or not height:
        return 1024, 1024

    ratio = width / height

    # Square (1:1) — 0.95 ≤ ratio ≤ 1.05
    if 0.95 <= ratio <= 1.05:
        return 1024, 1024

    # LANDSCAPE
    if ratio > 1.05:
        if ratio < 1.33:    return 1152, 896   # ~5:4  (1.29) — gap 1.05..1.33 now filled
        elif ratio < 1.44:  return 1184, 864   # ~4:3  (1.37)
        elif ratio < 1.63:  return 1248, 832   # ~3:2  (1.50)
        elif ratio < 2.02:  return 1344, 768   # ~16:9 (1.75)
        else:               return 1536, 672   # ~21:9 (2.29) — ultra-wide

    # PORTRAIT
    else:  # ratio < 0.95
        if ratio > 0.75:    return 896, 1152   # ~4:5  (0.78) — gap 0.80..0.95 now filled
        elif ratio > 0.70:  return 864, 1184   # ~3:4  (0.73) — was previously unused
        elif ratio > 0.62:  return 832, 1248   # ~2:3  (0.67)
        else:               return 768, 1344   # ~9:16 (0.57)


def _get_nano_banana_v25_dimensions(width: Optional[int], height: Optional[int]) -> tuple[int, int]:
    """
    Dimension mapping for google:4@1 (Nano Banana 2.5 — 10 supported ratios).
    Uses exact accepted 1K-tier dimensions.

    Exact 1K-tier dimensions (server-validated):
      Landscape : 1152×928 (5:4, 1.24), 1200×896 (4:3, 1.34), 1264×848 (3:2, 1.49),
                  1376×768 (16:9, 1.79), 1584×672 (21:9, 2.36)
      Square    : 1024×1024 (1:1)
      Portrait  : 928×1152 (4:5, 0.81), 896×1200 (3:4, 0.75), 848×1264 (2:3, 0.67),
                  768×1376 (9:16, 0.56)

    Midpoint boundaries:
      Landscape: 1.121 | 1.290 | 1.415 | 1.641 | 2.074
      Portrait:  0.903 | 0.776 | 0.709 | 0.615
    """
    if not width or not height:
        return 1024, 1024

    ratio = width / height

    if 0.903 <= ratio <= 1.121:
        return 1024, 1024  # 1:1

    if ratio > 1.121:
        if ratio < 1.290:   return 1152, 928   # 5:4  (1.24)
        elif ratio < 1.415: return 1200, 896   # 4:3  (1.34)
        elif ratio < 1.641: return 1264, 848   # 3:2  (1.49)
        elif ratio < 2.074: return 1376, 768   # 16:9 (1.79)
        else:               return 1584, 672   # 21:9 (2.36) — widest supported
    else:
        if ratio > 0.776:   return 928, 1152   # 4:5  (0.81)
        elif ratio > 0.709: return 896, 1200   # 3:4  (0.75)
        elif ratio > 0.615: return 848, 1264   # 2:3  (0.67)
        else:               return 768, 1376   # 9:16 (0.56) — tallest supported


def _get_nano_banana_v3_dimensions(width: Optional[int], height: Optional[int]) -> tuple[int, int]:
    """
    Dimension mapping for google:4@3 (Nano Banana 3.1 / image generation model).
    Supports 14 aspect ratios including extreme banner/header formats.

    Exact 1K-tier dimensions:
      Landscape : 1152×928 (5:4, 1.24), 1200×896 (4:3, 1.34), 1264×848 (3:2, 1.49),
                  1376×768 (16:9, 1.79), 1584×672 (21:9, 2.36)
      Square    : 1024×1024 (1:1)
      Portrait  : 928×1152 (4:5, 0.81), 896×1200 (3:4, 0.75), 848×1264 (2:3, 0.67),
                  768×1376 (9:16, 0.56)
      Extreme   : 2048×512  (4:1, 4.00), 1536×192 (8:1, 8.00),
                  512×2048  (1:4, 0.25), 192×1536 (1:8, 0.125)

    Midpoint boundaries (from error-validated supported dimensions):
      Landscape: 1.121 | 1.290 | 1.415 | 1.641 | 2.074 | 3.179 | 6.0
      Portrait:  0.903 | 0.776 | 0.709 | 0.615 | 0.404 | 0.188
    """
    if not width or not height:
        return 1024, 1024

    ratio = width / height

    if 0.903 <= ratio <= 1.121:
        return 1024, 1024  # 1:1

    if ratio > 1.121:
        if ratio < 1.290:   return 1152, 928   # 5:4  (1.24)
        elif ratio < 1.415: return 1200, 896   # 4:3  (1.34)
        elif ratio < 1.641: return 1264, 848   # 3:2  (1.49)
        elif ratio < 2.074: return 1376, 768   # 16:9 (1.79)
        elif ratio < 3.179: return 1584, 672   # 21:9 (2.36)
        elif ratio < 6.0:   return 2048, 512   # 4:1  (4.00) — banner/wide header
        else:               return 1536, 192   # 8:1  (8.00) — ultra-wide strip
    else:
        if ratio > 0.776:   return 928, 1152   # 4:5  (0.81)
        elif ratio > 0.709: return 896, 1200   # 3:4  (0.75)
        elif ratio > 0.615: return 848, 1264   # 2:3  (0.67)
        elif ratio > 0.404: return 768, 1376   # 9:16 (0.56)
        elif ratio > 0.188: return 512, 2048   # 1:4  (0.25) — tall banner
        else:               return 192, 1536   # 1:8  (0.125) — ultra-tall strip


def _get_flux_dimensions(width: Optional[int], height: Optional[int]) -> tuple[int, int]:
    """
    Map (width, height) to FLUX.2 Dev's official recommended dimension presets.
    FLUX supports any aspect ratio — both dimensions must be multiples of 16.
    Presets from official FLUX model docs (~1MP sweet spot):
      Landscape : 1152×896 (4:3, 1.29), 1216×832 (3:2, 1.46), 1344×768 (16:9, 1.75), 1536×640 (21:9, 2.40)
      Square    : 1024×1024 (1:1)
      Portrait  : 896×1152 (3:4, 0.78), 832×1216 (2:3, 0.68), 768×1344 (9:16, 0.57), 640×1536 (9:21, 0.42)

    Midpoint boundaries:
      Landscape: 1.05 | 1.374 | 1.606 | 2.075
      Portrait:  0.95 | 0.731 | 0.628 | 0.494
    """
    if not width or not height:
        return 1024, 1024

    ratio = width / height

    if 0.95 <= ratio <= 1.05:
        return 1024, 1024  # 1:1

    if ratio > 1.05:
        if ratio < 1.374:   return 1152, 896   # 4:3  (1.29)
        elif ratio < 1.606: return 1216, 832   # 3:2  (1.46)
        elif ratio < 2.075: return 1344, 768   # 16:9 (1.75)
        else:               return 1536, 640   # 21:9 (2.40)
    else:
        if ratio > 0.731:   return 896, 1152   # 3:4  (0.78)
        elif ratio > 0.628: return 832, 1216   # 2:3  (0.68)
        elif ratio > 0.494: return 768, 1344   # 9:16 (0.57)
        else:               return 640, 1536   # 9:21 (0.42)


# ==================== Low-level Inference Helpers ====================

INFERENCE_TIMEOUT = 60       # seconds per attempt — text-to-image
EDIT_INFERENCE_TIMEOUT = 60  # seconds per attempt — img2img (heavier, needs more time)
INFERENCE_MAX_ATTEMPTS = 2   # retry once before falling back

DEFAULT_NEGATIVE_PROMPT = (
    "text, words, letters, numbers, digits, alphabet, characters, glyphs, "
    "labels, captions, titles, headlines, subtitles, watermarks, signatures, "
    "typography, writing, handwriting, calligraphy, font, fonts, lettering, "
    "signage, signs, billboards, posters with text, banners with text, "
    "paragraphs, sentences, quotes, citations, logos with text, brand text, "
    "subtitles, ui text, menu text, overlay text, embedded text, "
    "infographic, org chart, diagram, flowchart, schematic, chart labels, "
    "speech bubble, caption box, label box, text overlay, watermark text, "
    "scientific labels, anatomical labels, equation, formula, mathematical notation, "
    "chemical formula, molecular labels, axis labels, legend text, "
    "misspelled text, gibberish text, garbled letters, random characters, "
    "asian characters, cyrillic, arabic script, hieroglyphs"
)

# Prefix injected into EVERY image generation prompt (text-to-image AND img2img edits)
# to suppress text in output. The double emphasis matters — diffusion models are
# more reliable when "no text" is repeated and structured.
NO_TEXT_PREFIX = (
    "Photograph with absolutely NO text, NO words, NO letters, NO numbers, "
    "NO labels, NO captions, NO titles, NO headlines, NO watermarks, "
    "NO typography, NO signage, NO writing of any kind anywhere in the image. "
    "NO scientific labels, NO equations, NO formulas, NO diagrams with annotations, "
    "NO infographic text, NO chart labels, NO axis labels, NO legends. "
    "Pure visual scene only — image must contain ZERO readable characters "
    "in any language or script. Subject: "
)


# ==================== Prompt Sanitization ====================

import re as _re

# Phrases that, if present in a user prompt, dramatically increase the chance
# of the diffusion model rendering text/letters in the output. We strip them.
_TEXT_TRIGGER_PATTERNS = [
    _re.compile(r'\b(?:reads?|reading|saying|says|titled|labeled|labelled|inscribed|written|spelled|spelling)\b[^.,;]*', _re.IGNORECASE),
    _re.compile(r'\b(?:with|showing|featuring|displaying|containing)\s+(?:the\s+)?(?:text|words?|letters?|caption|title|headline|sign|signage|label|watermark|logo)\b[^.,;]*', _re.IGNORECASE),
    _re.compile(r'\b(?:text|words?|letters?|captions?|titles?|headlines?|watermarks?|typography|signage|writing|paragraphs?|sentences?)\s+(?:that|which|saying|reading|spelling)\b[^.,;]*', _re.IGNORECASE),
    _re.compile(r'\b(?:billboard|sign|poster|banner|placard)\s+(?:reads?|says?|saying|with|that)\b[^.,;]*', _re.IGNORECASE),
    # Strip "<Topic> cycle/process/diagram/system/method/equation/formula/theory/effect/law/principle"
    # — these named-concept patterns are the #1 cause of topic names being rendered as text
    # (e.g. "Krebs cycle" → "CELLEBREBS CRYCLO" in image output).
    _re.compile(r"\b(?:[A-Z][a-zA-Z'\-]*\s+){1,3}(?:cycle|process|diagram|chart|graph|equation|formula|theory|effect|law|principle|hypothesis|model|method|methodology|system|pipeline|workflow|lifecycle|phase|stage)s?\b", _re.IGNORECASE),
    # Strip "diagram/chart/illustration of <X>" — same root cause
    _re.compile(r'\b(?:diagram|chart|graph|infographic|illustration|schematic|figure|labeled\s+illustration)\s+of\b[^.,;]*', _re.IGNORECASE),
]

# Strip any quoted strings ("..." or '...' or “...”) — these are the #1 cause
# of literal text being rendered into images.
_QUOTED_STRING_PATTERN = _re.compile(r"""(?:["“”'‘’])[^"“”'‘’]{1,200}(?:["“”'‘’])""")

# 4-digit years (1900-2099) — diffusion models render years as text very
# reliably (e.g. "Global Energy Outlook 2025" → "2025" baked into the image).
_YEAR_PATTERN = _re.compile(r"\b(?:19|20)\d{2}\b")

# Quarter / fiscal-year markers (Q1, FY24, H1) — same risk.
_QUARTER_PATTERN = _re.compile(r"\b(?:Q[1-4]|FY\d{2,4}|H[12])\b")

# 3+ consecutive Capitalized words = proper-noun phrase (e.g. "Global Energy
# Outlook", "Bank Of America"). Strips the whole phrase when detected.
_PROPER_NOUN_PHRASE_PATTERN = _re.compile(
    r"(?:[A-Z][a-zA-Z'\-]+\s+){2,}[A-Z][a-zA-Z'\-]+"
)


def _sanitize_image_prompt(prompt: str) -> str:
    """Strip phrases that prompt diffusion models to render text into images.

    Defense layers (any of these tokens can leak as readable text in the
    rendered image regardless of NO_TEXT_PREFIX / negative_prompt):
      1. Quoted strings — rendered literally.
      2. Explicit text-trigger phrases ("labeled X", "saying Y", named-cycle
         patterns like "Krebs cycle").
      3. Years and quarters — render reliably as date text.
      4. Multi-word proper-noun phrases — render as ghosted topic letters.
    """
    if not prompt:
        return prompt
    cleaned = _QUOTED_STRING_PATTERN.sub("", prompt)
    for pat in _TEXT_TRIGGER_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = _YEAR_PATTERN.sub("", cleaned)
    cleaned = _QUARTER_PATTERN.sub("", cleaned)
    cleaned = _PROPER_NOUN_PHRASE_PATTERN.sub("", cleaned)
    # Collapse whitespace / leftover punctuation
    cleaned = _re.sub(r"\s{2,}", " ", cleaned)
    cleaned = _re.sub(r"\s+([.,;:])", r"\1", cleaned)
    cleaned = cleaned.strip(" .,;:-")
    return cleaned


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_not_exception_type(ImageGenTimeoutError),
    before_sleep=lambda retry_state: logger.warning(f"🔄 [IMAGE_GEN] Retrying image generation (attempt {retry_state.attempt_number}) due to: {retry_state.outcome.exception()}")
)
async def _generate_single_image(prompt: str, width: int = 1024, height: int = 1024, model: str = None, user_id: str = None, user_email: str = None) -> tuple:
    """
    Generate a single image via the configured provider.
    Returns (image_data_uri, actual_model_used) tuple for accurate billing.
    """
    model = model or EDIT_CAPABLE_MODEL
    # GUARD: prompts must be TEXT. Client bugs have leaked base64 image data
    # (chat attachments / data-URI srcs) into imageDescription — observed a
    # 529K-char prompt in prod. Strip data-URIs / long base64 runs and log the
    # head+tail LOUDLY so the leak's source is identifiable from logs.
    if len(prompt) > 5000:
        _stripped = _re.sub(r'data:[a-zA-Z0-9/+.\-]+;base64,[A-Za-z0-9+/=\s]+|[A-Za-z0-9+/=]{500,}', ' ', prompt)
        logger.error(
            f"🚨 [IMAGE_GEN] OVERSIZED prompt ({len(prompt)} chars) — stripped embedded base64 → {len(_stripped)} chars. "
            f"head={prompt[:80]!r} tail={prompt[-120:]!r}"
        )
        prompt = _stripped[:3000]
    # Strip any quoted strings / explicit "text/label/caption" triggers from user prompt,
    # then inject the strict NO-TEXT prefix to suppress text generation in images.
    sanitized = _sanitize_image_prompt(prompt)
    if sanitized != prompt:
        logger.info(f"🧹 [IMAGE_GEN] Sanitized prompt to remove text-trigger phrases (len {len(prompt)}→{len(sanitized)})")
    prompt = f"{NO_TEXT_PREFIX}{sanitized}"
    logger.info(f"🖼️ [IMAGE_GEN] Model {model} — using {width}x{height} output")

    provider = get_provider()

    for attempt in range(1, INFERENCE_MAX_ATTEMPTS + 1):
        try:
            result: ImageGenResult = await provider.generate(
                prompt=prompt,
                negative_prompt=DEFAULT_NEGATIVE_PROMPT,
                width=width,
                height=height,
                model=model,
                timeout=INFERENCE_TIMEOUT,
            )
            return result.data_uri, model
        except ImageGenTimeoutError:
            logger.warning(f"⏱️ [IMAGE_GEN] Generation attempt {attempt}/{INFERENCE_MAX_ATTEMPTS} timed out after {INFERENCE_TIMEOUT}s (model={model}, prompt='{prompt[:40]}...')")

    raise ImageGenTimeoutError(f"Image generation timed out after all attempts (model={model})")


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_not_exception_type(ImageGenTimeoutError),
    before_sleep=lambda retry_state: logger.warning(f"🔄 [IMAGE_GEN] Retrying image edit (attempt {retry_state.attempt_number}) due to: {retry_state.outcome.exception()}")
)
async def _edit_single_image(prompt: str, source_image: str, width: int = 1024, height: int = 1024, model: str = None, strength: Optional[float] = None, user_id: str = None, user_email: str = None) -> tuple:
    """
    Edit a single image via the configured provider.
    Returns (image_data_uri, actual_model_used) tuple for accurate billing.
    """
    model = model or EDIT_CAPABLE_MODEL
    provider = get_provider()

    if not provider.supports_edit():
        raise ValueError(f"Current image generation provider does not support image editing.")

    # Strip text-trigger phrases and inject NO-TEXT prefix on edits as well —
    # img2img is just as prone to leaking captions/watermarks as text-to-image.
    sanitized = _sanitize_image_prompt(prompt)
    if sanitized != prompt:
        logger.info(f"🧹 [IMAGE_GEN_EDIT] Sanitized prompt to remove text-trigger phrases (len {len(prompt)}→{len(sanitized)})")
    prompt = f"{NO_TEXT_PREFIX}{sanitized}"

    logger.info(f"🖼️ [IMAGE_GEN_EDIT] Editing image with model {model}")

    for attempt in range(1, INFERENCE_MAX_ATTEMPTS + 1):
        try:
            result: ImageGenResult = await provider.edit(
                prompt=prompt,
                negative_prompt=DEFAULT_NEGATIVE_PROMPT,
                source_image=source_image,
                width=width,
                height=height,
                model=model,
                strength=strength,
                timeout=EDIT_INFERENCE_TIMEOUT,
            )
            return result.data_uri, model
        except ImageGenTimeoutError:
            logger.warning(f"⏱️ [IMAGE_GEN_EDIT] Edit attempt {attempt}/{INFERENCE_MAX_ATTEMPTS} timed out after {EDIT_INFERENCE_TIMEOUT}s (model={model}, prompt='{prompt[:40]}...')")

    raise ImageGenTimeoutError(f"Image edit timed out after all attempts (model={model})")


# ==================== Endpoints ====================

@router.post("/image-gen/generate", response_model=ImageGenResponse)
async def generate_image(req: Request):
    """
    Generate a single image using the configured image generation backend.
    """
    # Manually parse body — BaseHTTPMiddleware stacking can cause body to arrive as raw bytes
    # instead of parsed JSON, leading to Pydantic model_attributes_type errors.
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 🔒 SECURITY: Strip user_id/user_email from body — always use JWT-authenticated identity
    body.pop('user_id', None)
    body.pop('user_email', None)

    try:
        request = ImageGenRequest(**body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid request: {e}")

    # Secure user_id from JWT
    final_user_id = get_secure_user_id(req)

    # --- CREDIT CHECK ---
    if BILLING_AVAILABLE and final_user_id:
        try:
            credit_check = check_user_credits(final_user_id, 0)
            if not credit_check['success']:
                 logger.error(f"❌ [IMAGE_GEN] Insufficient credits for {final_user_id}")
                 return ImageGenResponse(success=False, message="Insufficient credits. Please purchase credits to continue.")
        except Exception as e:
            logger.error(f"⚠️ [IMAGE_GEN] Credit check system error — blocking request: {e}")
            return ImageGenResponse(success=False, message="Credit verification temporarily unavailable. Please retry.")

    # Calculate optimal dimensions — Flux Dev, use FLUX dimension presets
    target_w, target_h = _get_flux_dimensions(request.width, request.height)
    logger.info(f"🖼️ [IMAGE_GEN] Model: {request.model or EDIT_CAPABLE_MODEL} | Prompt: '{request.prompt[:60]}...' | Size: {target_w}x{target_h}")

    try:
        image_data, billed_model = await _generate_single_image(
            prompt=request.prompt,
            width=target_w,
            height=target_h,
            model=request.model,
            user_id=final_user_id,
            user_email=final_user_id,
        )
        
        image_data = _compress_data_uri(image_data)
        logger.info(f"✅ [IMAGE_GEN] Image generated ({len(image_data)} chars data URI, model={billed_model})")

        # --- BILLING TRACKING ---
        if BILLING_AVAILABLE and final_user_id:
            try:
                token_cost = _get_image_gen_token_cost(billed_model)
                track_query_usage(
                    user_id=final_user_id,
                    email=final_user_id,
                    model='image_generation',
                    input_tokens=0,
                    output_tokens=0,
                    cached_tokens=0,
                    internet_grounding_cost=token_cost
                )
                logger.info(f"💠 [IMAGE_GEN] Usage tracked: {token_cost} token-units (model={billed_model})")
            except Exception as e:
                logger.error(f"❌ [IMAGE_GEN] Billing track failed: {e}")

        return ImageGenResponse(
            success=True, 
            image_data=image_data
        )

    except Exception as e:
        error_msg = str(e)

        # Check for credit errors and raise HTTP 402 (match llm_api logic)
        if "insufficient_credits" in error_msg.lower() or "negative balance" in error_msg.lower():
            logger.info("💰 [IMAGE_GEN] Raising 402 for insufficient credits")
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": "Insufficient credits. Please purchase more credits to continue."
                }
            )

        # Single model — no fallback chain needed.
        logger.error(f"❌ [IMAGE_GEN] Generation failed: {e}", exc_info=True)
        return ImageGenResponse(success=False, message=str(e))


@router.post("/image-gen/edit", response_model=ImageGenResponse)
async def edit_image(req: Request):
    """
    Edit an existing image using the configured image generation backend.
    """
    # Manually parse body — BaseHTTPMiddleware stacking can cause body to arrive as raw bytes
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 🔒 SECURITY: Strip user_id/user_email from body — always use JWT-authenticated identity
    body.pop('user_id', None)
    body.pop('user_email', None)

    try:
        request = ImageGenEditRequest(**body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid request: {e}")

    # Secure user_id from JWT
    final_user_id = get_secure_user_id(req)

    # --- CREDIT CHECK ---
    if BILLING_AVAILABLE and final_user_id:
        try:
            credit_check = check_user_credits(final_user_id, 0)
            if not credit_check['success']:
                 logger.error(f"❌ [IMAGE_GEN_EDIT] Insufficient credits for {final_user_id}")
                 return ImageGenResponse(success=False, message="Insufficient credits. Please purchase credits to continue.")
        except Exception as e:
            logger.error(f"⚠️ [IMAGE_GEN_EDIT] Credit check system error — blocking request: {e}")
            return ImageGenResponse(success=False, message="Credit verification temporarily unavailable. Please retry.")

    logger.info(f"🖼️ [IMAGE_GEN_EDIT] Edit image | Prompt: '{request.prompt[:50]}...'")

    try:
        image_data, billed_model = await _edit_single_image(
            prompt=request.prompt,
            source_image=request.source_image,
            width=request.width or 1024,
            height=request.height or 1024,
            model=EDIT_CAPABLE_MODEL,
            user_id=final_user_id,
            user_email=final_user_id,
        )

        if image_data:
            image_data = _compress_data_uri(image_data)
            logger.info(f"✅ [IMAGE_GEN_EDIT] Edit succeeded (model={billed_model})")

            # --- BILLING TRACKING ---
            if BILLING_AVAILABLE and final_user_id:
                try:
                    token_cost = _get_image_gen_token_cost(billed_model)
                    track_query_usage(
                        user_id=final_user_id,
                        email=final_user_id,
                        model='image_generation',
                        input_tokens=0,
                        output_tokens=0,
                        cached_tokens=0,
                        internet_grounding_cost=token_cost
                    )
                    logger.info(f"💠 [IMAGE_GEN_EDIT] Usage tracked: {token_cost} token-units (model={billed_model})")
                except Exception as e:
                    logger.error(f"❌ [IMAGE_GEN_EDIT] Billing track failed: {e}")

            return ImageGenResponse(
                success=True,
                image_data=image_data
            )
        else:
            return ImageGenResponse(success=False, message="Edit returned no image")

    except Exception as e:
        error_msg = str(e)

        # Check for credit errors and raise HTTP 402
        if "insufficient_credits" in error_msg.lower() or "negative balance" in error_msg.lower():
            logger.info("💰 [IMAGE_GEN_EDIT] Raising 402 for insufficient credits")
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": "Insufficient credits. Please purchase more credits to continue."
                }
            )

        logger.error(f"❌ [IMAGE_GEN_EDIT] Edit failed: {error_msg}")
        return ImageGenResponse(success=False, message=f"Image edit failed: {error_msg}")