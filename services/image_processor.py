# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Image and Video Processor Service
Handles extraction, upload, and management of images and videos for Reports, Presentations, and Printables.
Moves media to S3 to keep database size low and ensure secure storage.
"""

import re
import base64
import hashlib
import time
import logging
import io
import json
import os
import httpx
from typing import Tuple, List, Set, Dict, Any
from datetime import datetime

# Import S3 client from root
import bucket
from utils import get_user_id
from security.url_validator import is_safe_url

logger = logging.getLogger(__name__)

# S3 bucket name for internal URI scheme (s3://<bucket>/<key>)
_S3_BUCKET = os.getenv("BUCKET_NAME", "citra-documents")
_S3_PREFIX = f"s3://{_S3_BUCKET}/"

class ImageProcessor:
    def __init__(self):
        self.s3_base_url = _S3_PREFIX

    def _is_foreign_key(self, key: str, user_id: str, doc_type: str, doc_id: str) -> bool:
        """
        Check if an S3 key belongs to a different document than the one being saved.
        Returns True if the key points to another document's prefix (cross-document reference).
        E.g. key = "userX/presentations/OLD_ID/images/file.png" but we're saving doc_id = "NEW_ID"
        """
        unique_code = get_user_id(user_id)
        expected_prefix = f"{unique_code}/{doc_type}/{doc_id}/"
        return not key.startswith(expected_prefix)

    def _copy_foreign_media(self, key: str, user_id: str, doc_type: str, doc_id: str) -> str:
        """
        Copy a foreign S3 file into the current document's prefix.
        Preserves the media subfolder (images/, videos/, icons/) and filename.
        Returns the new s3:// URI, or the original URI on failure.
        """
        unique_code = get_user_id(user_id)
        # Extract media subfolder + filename from the key
        # Key format: {some_user}/{some_type}/{some_id}/{folder}/{filename}
        parts = key.split("/")
        # We need at least 4 parts: user/type/id/folder/filename...
        if len(parts) >= 4:
            # Take everything after the 3rd slash (folder/filename)
            media_path = "/".join(parts[3:])
        else:
            # Fallback: use the full key as filename under images/
            media_path = f"images/{parts[-1]}"

        new_key = f"{unique_code}/{doc_type}/{doc_id}/{media_path}"

        if bucket.copy_file(key, new_key):
            logger.info(f"📋 [CROSS-DOC] Copied foreign media to local: {key} → {new_key}")
            return f"{_S3_PREFIX}{new_key}"
        else:
            logger.warning(f"⚠️ [CROSS-DOC] Failed to copy foreign media, keeping original reference: {key}")
            return f"{_S3_PREFIX}{key}"

    def _generate_image_key(self, user_id: str, doc_type: str, doc_id: str, image_data: bytes, extension: str = "png") -> str:
        """Generate a unique S3 key for an image."""
        # Sanitize user_id
        unique_code = get_user_id(user_id)
        
        # Hash content for deduplication (optional) or just uniqueness
        content_hash = hashlib.md5(image_data).hexdigest()[:12]
        timestamp = int(time.time() * 1000)
        # Structure: {unique_code}/{doc_type}/{doc_id}/images/{timestamp}_{hash}.{ext}
        key = f"{unique_code}/{doc_type}/{doc_id}/images/{timestamp}_{content_hash}.{extension}"
        return key

    def _generate_video_key(self, user_id: str, doc_type: str, doc_id: str, video_data: bytes, extension: str = "mp4") -> str:
        """Generate a unique S3 key for a video."""
        unique_code = get_user_id(user_id)
        content_hash = hashlib.md5(video_data).hexdigest()[:12]
        timestamp = int(time.time() * 1000)
        # Structure: {unique_code}/{doc_type}/{doc_id}/videos/{timestamp}_{hash}.{ext}
        key = f"{unique_code}/{doc_type}/{doc_id}/videos/{timestamp}_{content_hash}.{extension}"
        return key

    def _get_extension_from_mime(self, mime_type: str) -> str:
        if "jpeg" in mime_type or "jpg" in mime_type:
            return "jpg"
        if "png" in mime_type:
            return "png"
        if "gif" in mime_type:
            return "gif"
        if "webp" in mime_type:
            return "webp"
        return "png"

    def _get_video_extension_from_mime(self, mime_type: str) -> str:
        """Get video file extension from MIME type."""
        if "mp4" in mime_type:
            return "mp4"
        if "webm" in mime_type:
            return "webm"
        if "ogg" in mime_type:
            return "ogg"
        if "quicktime" in mime_type or "mov" in mime_type:
            return "mov"
        if "avi" in mime_type:
            return "avi"
        return "mp4"

    def upload_base64_video(self, base64_str: str, user_id: str, doc_type: str, doc_id: str) -> str:
        """
        Upload a single base64 video string to S3.
        Returns the S3 URL (s3://...).
        """
        try:
            # Extract mime type and data
            # Format: data:video/mp4;base64,AAAAHGZ0eXBpc29...
            if "," in base64_str:
                header, data = base64_str.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0] if ":" in header else "video/mp4"
            else:
                data = base64_str
                mime_type = "video/mp4"

            extension = self._get_video_extension_from_mime(mime_type)
            video_bytes = base64.b64decode(data)
            
            key = self._generate_video_key(user_id, doc_type, doc_id, video_bytes, extension)
            
            # Upload using s3_client
            uploaded_url = bucket.upload_file(video_bytes, key, mime_type)
            
            logger.info(f"🎬 [VIDEO] Uploaded video to S3: {key} ({len(video_bytes)} bytes)")
            return f"{_S3_PREFIX}{key}"
            
        except Exception as e:
            logger.error(f"Failed to upload video: {e}")
            raise

    def upload_base64_image(self, base64_str: str, user_id: str, doc_type: str, doc_id: str) -> str:
        """
        Upload a single base64 string to S3.
        Returns the S3 URL (s3://...).
        """
        try:
            # Extract mime type and data
            # Format: data:image/png;base64,iVBORw0KGgo...
            if "," in base64_str:
                header, data = base64_str.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
            else:
                data = base64_str
                mime_type = "image/png"

            extension = self._get_extension_from_mime(mime_type)
            image_bytes = base64.b64decode(data)
            
            key = self._generate_image_key(user_id, doc_type, doc_id, image_bytes, extension)
            
            # Upload using s3_client
            # Note: bucket.upload_file returns https URL, but we want to store key mostly to be environment agnostic?
            # Actually, bucket.upload_file returns full URL.
            # But the requirement says "s3://citra-ai/..." for internal storage or similar.
            # Let's see what upload_file_to_s3 returns.
            # It returns `https://{bucket}.s3.{region}.amazonaws.com/{env}/{key}`.
            # We can store that, OR we can store specific internal reference.
            # Storing the full URL is easiest for now, BUT if we want Presigned URLs, we need the KEY.
            # upload_file_to_s3 takes `s3_key`.
            
            uploaded_url = bucket.upload_file(image_bytes, key, mime_type)
            
            # extract key from URL isn't great if URL format changes.
            # But we know the key we passed: `key`.
            # Note: upload_file_to_s3 prepends env_prefix.
            # So the real key in S3 is `env/key`.
            # For "s3://" style, we should probably construct our own reference that we can parse later.
            # Or just store "s3://{key}" and let the reader handle env prefix? 
            # s3_client logic:
            # generate_presigned_url(key) -> adds env prefix.
            # So we should store just the `key` (without env).
            
            return f"{_S3_PREFIX}{key}"
            
        except Exception as e:
            logger.error(f"Failed to upload image: {e}")
            raise

    # ── Known external image hosts whose URLs expire ──
    EPHEMERAL_IMAGE_HOSTS = [
        "im.runware.ai",       # Runware CDN – URLs expire after ~30 days
    ]

    def _is_ephemeral_url(self, url: str) -> bool:
        """Return True if *url* belongs to a CDN whose links are known to expire."""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
            return any(host.endswith(h) for h in self.EPHEMERAL_IMAGE_HOSTS)
        except Exception:
            return False

    async def upload_url_image(self, url: str, user_id: str, doc_type: str, doc_id: str) -> str:
        """
        Download an image from an external URL and upload it to S3.
        Returns the S3 URI (s3://citra-ai/...).
        """
        if not is_safe_url(url):
            raise ValueError("URL targets a blocked address")
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

            image_bytes = response.content
            content_type = response.headers.get("content-type", "image/png")

            # Derive extension from Content-Type or URL
            extension = self._get_extension_from_mime(content_type)
            if extension == "png":  # fallback – try from URL path
                import os
                url_ext = os.path.splitext(url.split("?")[0])[1].lstrip(".")
                if url_ext in ("jpg", "jpeg", "png", "gif", "webp"):
                    extension = url_ext

            key = self._generate_image_key(user_id, doc_type, doc_id, image_bytes, extension)
            bucket.upload_file(image_bytes, key, content_type)

            logger.info(f"🔄 [IMAGE] Downloaded external URL and uploaded to S3: {url[:80]}... -> {key}")
            return f"{_S3_PREFIX}{key}"

        except Exception as e:
            logger.error(f"Failed to download and upload external image {url[:120]}: {e}")
            raise

    def _generate_icon_key(self, user_id: str, doc_type: str, doc_id: str, icon_name: str) -> str:
        """Generate a unique S3 key for an icon SVG."""
        unique_code = get_user_id(user_id)
        # Sanitize icon name for S3 key
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', icon_name)
        # Structure: {unique_code}/{doc_type}/{doc_id}/icons/{icon_name}.svg
        key = f"{unique_code}/{doc_type}/{doc_id}/icons/{safe_name}.svg"
        return key

    def upload_svg_icon(self, svg_path: str, icon_name: str, user_id: str, doc_type: str, doc_id: str, fill_color: str = "#ffffff") -> str:
        """
        Upload an SVG icon to S3.
        Creates SVG from path data, uploads, returns S3 URL.
        
        Args:
            svg_path: SVG path data (d attribute)
            icon_name: Original icon name (e.g., "rocket", "lucide:rocket")
            user_id: User identifier
            doc_type: Document type ("presentations", "reports")
            doc_id: Document ID
            fill_color: Icon stroke color
        
        Returns:
            S3 URL (s3://citra-ai/...)
        """
        try:
            # Create full SVG content
            # Robust check: If svg_path is already a full SVG, use it directly
            if svg_path.strip().startswith('<svg'):
                svg_content = svg_path
            else:
                svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{fill_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="{svg_path}"/></svg>'''
            
            svg_bytes = svg_content.encode('utf-8')
            key = self._generate_icon_key(user_id, doc_type, doc_id, icon_name)
            
            # Upload to S3
            bucket.upload_file(svg_bytes, key, "image/svg+xml")
            
            logger.info(f"🎨 [ICON] Uploaded icon to S3: {icon_name} -> {key}")
            return f"{_S3_PREFIX}{key}"
            
        except Exception as e:
            logger.error(f"Failed to upload icon {icon_name}: {e}")
            raise

    async def process_report_content(self, pages: List[Dict[str, Any]], user_id: str, report_id: str) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """
        Process HTML content in report pages.
        Extract Base64 -> Upload -> Replace with s3:// URL.
        Returns: (Updated Pages, Set of Active S3 Keys)
        """
        active_keys = set()
        updated_pages = []

        # Regex for finding data:image src
        # src="data:image/png;base64,..."
        # Captures: 1=quote, 2=mime, 3=data
        img_regex = re.compile(r'src=(["\'])data:(image/[a-zA-Z]+);base64,([^"\']+)\1')

        for page in pages:
            content = page.get("content", "")
            if not content:
                updated_pages.append(page)
                continue

            def replace_match(match):
                quote = match.group(1)
                mime_type = match.group(2)
                b64_data = match.group(3)
                full_b64 = f"data:{mime_type};base64,{b64_data}"
                
                try:
                    s3_uri = self.upload_base64_image(full_b64, user_id, "reports", report_id)
                    # Extract key from s3_uri: s3://citra-ai/{key}
                    key = s3_uri.replace(_S3_PREFIX, "")
                    active_keys.add(key)
                    return f"src={quote}{s3_uri}{quote}"
                except Exception as e:
                    logger.error(f"Failed to process image in report {report_id}: {e}")
                    raise

            new_content = img_regex.sub(replace_match, content)
            
            # Also find existing s3:// urls to add to active_keys (so we don't delete them)
            # Regex for src="s3://<bucket>/..."
            s3_regex = re.compile(rf'src=(["\'])' + re.escape(_S3_PREFIX) + r'([^"\']+)\1')
            for match in s3_regex.finditer(new_content):
                active_keys.add(match.group(2))
                
            page["content"] = new_content
            
            # CRITICAL: Sanitize presigned URLs back to s3:// before saving
            presigned_regex = re.compile(r'src=(["\'])(https://[^"\']*\.amazonaws\.com/[^"\']*\?[^"\']*X-Amz-[^"\']+)\1')
            
            def sanitize_presigned(match):
                quote = match.group(1)
                url = match.group(2)
                try:
                    clean_url = url.split("?")[0]
                    unique_code = get_user_id(user_id)
                    if unique_code in clean_url:
                        key_part = clean_url[clean_url.find(unique_code):]
                        s3_uri = f"{_S3_PREFIX}{key_part}"
                        active_keys.add(key_part)
                        logger.info(f"🔄 [REPORT] Sanitized presigned URL back to: {key_part}")
                        return f"src={quote}{s3_uri}{quote}"
                except Exception as e:
                    logger.error(f"Failed to sanitize presigned URL in report: {e}")
                return match.group(0)
            
            page["content"] = presigned_regex.sub(sanitize_presigned, page["content"])
            
            # CRITICAL: Migrate ephemeral external image URLs (e.g. Runware CDN) to S3
            # Find all <img src="https://..."> that are NOT s3, NOT amazonaws, NOT base64
            ephemeral_regex = re.compile(r'src=(["\'])(https?://[^"\']+)\1')
            ephemeral_replacements = {}  # url -> s3_uri
            
            for match in ephemeral_regex.finditer(page["content"]):
                url = match.group(2)
                # Skip URLs we've already handled (s3://, amazonaws, base64)
                if _S3_PREFIX in url or ".amazonaws.com/" in url:
                    continue
                if self._is_ephemeral_url(url):
                    if url not in ephemeral_replacements:
                        try:
                            s3_uri = await self.upload_url_image(url, user_id, "reports", report_id)
                            ephemeral_replacements[url] = s3_uri
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                            logger.info(f"📥 [REPORT] Migrated ephemeral URL to S3: {url[:80]}...")
                        except Exception as e:
                            logger.warning(f"⚠️ [REPORT] Could not migrate ephemeral URL, keeping original: {e}")
            
            # Apply replacements
            current_content = page["content"]
            for old_url, new_s3_uri in ephemeral_replacements.items():
                current_content = current_content.replace(old_url, new_s3_uri)
            page["content"] = current_content
            
            updated_pages.append(page)

        return updated_pages, active_keys

    async def process_printable_PAGES(self, PAGES: List[Dict[str, Any]], user_id: str, printable_id: str) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """
        Process printable PAGES JSON.
        Iterate elements, find type='image' or 'icon', process and upload to S3.
        Returns: (Updated PAGES, Set of Active S3 Keys)
        """
        active_keys = set()
        updated_PAGES = []

        for PAGE in PAGES:
            elements = PAGE.get("elements", [])
            updated_elements = []
            
            for el in elements:
                # Process IMAGE elements
                if el.get("type") == "image" and "src" in el:
                    src = el["src"]
                    if src.startswith("data:image"):
                        try:
                            s3_uri = self.upload_base64_image(src, user_id, "printables", printable_id)
                            el["src"] = s3_uri
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                        except Exception as e:
                            logger.error(f"Failed to process image element in printable {printable_id}: {e}")
                            raise
                    elif src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        # Copy foreign media to this document's prefix
                        if self._is_foreign_key(key, user_id, "printables", printable_id):
                            new_uri = self._copy_foreign_media(key, user_id, "printables", printable_id)
                            el["src"] = new_uri
                            key = new_uri.replace(_S3_PREFIX, "")
                        active_keys.add(key)
                    elif src.startswith("http") and ".amazonaws.com/" in src:
                        # CRITICAL: Detect existing Presigned URL and convert back to s3:// key
                        try:
                            clean_url = src.split("?")[0]
                            unique_code = get_user_id(user_id)
                            if unique_code in clean_url:
                                key_part = clean_url[clean_url.find(unique_code):]
                                # Copy foreign media to this document's prefix
                                if self._is_foreign_key(key_part, user_id, "printables", printable_id):
                                    new_uri = self._copy_foreign_media(key_part, user_id, "printables", printable_id)
                                    el["src"] = new_uri
                                    key_part = new_uri.replace(_S3_PREFIX, "")
                                else:
                                    el["src"] = f"{_S3_PREFIX}{key_part}"
                                active_keys.add(key_part)
                                logger.info(f"🔄 [PRINTABLE] Converted presigned URL back to storage format: {key_part}")
                        except Exception as e:
                            logger.error(f"Failed to reverse presigned URL to key in printable: {e}")
                    elif src.startswith("http") and self._is_ephemeral_url(src):
                        # CRITICAL: External ephemeral URL (e.g. Runware CDN) – download and upload to S3
                        try:
                            s3_uri = await self.upload_url_image(src, user_id, "printables", printable_id)
                            el["src"] = s3_uri
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                            logger.info(f"📥 [PRINTABLE] Migrated ephemeral URL to S3: {src[:80]}...")
                        except Exception as e:
                            logger.warning(f"⚠️ [PRINTABLE] Could not migrate ephemeral URL, keeping original: {e}")
                
                # Process ICON elements - upload SVG to S3 for consistency
                elif el.get("type") == "icon" and el.get("svgPath"):
                    svg_path = el["svgPath"]
                    icon_name = el.get("resolvedIconName") or el.get("iconName") or "icon"
                    fill_color = el.get("fill", "#ffffff")
                    svg_src = el.get("svgSrc", "")
                    
                    # Check if already has S3 URL
                    if svg_src.startswith(_S3_PREFIX):
                        key = svg_src.replace(_S3_PREFIX, "")
                        # Copy foreign media to this document's prefix
                        if self._is_foreign_key(key, user_id, "printables", printable_id):
                            new_uri = self._copy_foreign_media(key, user_id, "printables", printable_id)
                            el["svgSrc"] = new_uri
                            key = new_uri.replace(_S3_PREFIX, "")
                        active_keys.add(key)
                    elif svg_src.startswith("http") and ".amazonaws.com/" in svg_src:
                        # CRITICAL: Detect existing Presigned URL and convert back to s3:// key (skip re-upload)
                        try:
                            clean_url = svg_src.split("?")[0]
                            unique_code = get_user_id(user_id)
                            if unique_code in clean_url:
                                key_part = clean_url[clean_url.find(unique_code):]
                                # Copy foreign media to this document's prefix
                                if self._is_foreign_key(key_part, user_id, "printables", printable_id):
                                    new_uri = self._copy_foreign_media(key_part, user_id, "printables", printable_id)
                                    el["svgSrc"] = new_uri
                                    key_part = new_uri.replace(_S3_PREFIX, "")
                                else:
                                    el["svgSrc"] = f"{_S3_PREFIX}{key_part}"
                                active_keys.add(key_part)
                                logger.info(f"🔄 [PRINTABLE ICON] Converted presigned URL back to storage format: {key_part}")
                        except Exception as e:
                            logger.error(f"Failed to reverse icon presigned URL to key in printable: {e}")
                    else:
                        # Upload icon SVG to S3 (only for NEW icons)
                        try:
                            s3_uri = self.upload_svg_icon(svg_path, icon_name, user_id, "printables", printable_id, fill_color)
                            el["svgSrc"] = s3_uri  # Store S3 URL for the SVG
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                        except Exception as e:
                            logger.error(f"Failed to upload icon {icon_name} in printable: {e}")
                
                # Process VIDEO elements - upload to S3 (local uploads only, not external URLs)
                elif el.get("type") == "video" and "src" in el:
                    src = el["src"]
                    video_type = el.get("videoType", "local")
                    
                    # Only process local/recorded videos (base64), skip external URLs (youtube, vimeo, etc.)
                    if video_type in ["local", "recorded"] or src.startswith("data:video"):
                        if src.startswith("data:video"):
                            try:
                                s3_uri = self.upload_base64_video(src, user_id, "printables", printable_id)
                                el["src"] = s3_uri
                                key = s3_uri.replace(_S3_PREFIX, "")
                                active_keys.add(key)
                                logger.info(f"🎬 [PRINTABLE] Uploaded video to S3: {key}")
                            except Exception as e:
                                logger.error(f"Failed to process video element in printable {printable_id}: {e}")
                                raise
                        elif src.startswith(_S3_PREFIX):
                            key = src.replace(_S3_PREFIX, "")
                            # Copy foreign media to this document's prefix
                            if self._is_foreign_key(key, user_id, "printables", printable_id):
                                new_uri = self._copy_foreign_media(key, user_id, "printables", printable_id)
                                el["src"] = new_uri
                                key = new_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                        elif src.startswith("http") and ".amazonaws.com/" in src:
                            # Convert presigned URL back to s3:// key
                            try:
                                clean_url = src.split("?")[0]
                                unique_code = get_user_id(user_id)
                                if unique_code in clean_url:
                                    key_part = clean_url[clean_url.find(unique_code):]
                                    # Copy foreign media to this document's prefix
                                    if self._is_foreign_key(key_part, user_id, "printables", printable_id):
                                        new_uri = self._copy_foreign_media(key_part, user_id, "printables", printable_id)
                                        el["src"] = new_uri
                                        key_part = new_uri.replace(_S3_PREFIX, "")
                                    else:
                                        el["src"] = f"{_S3_PREFIX}{key_part}"
                                    active_keys.add(key_part)
                                    logger.info(f"🔄 [PRINTABLE VIDEO] Converted presigned URL back to storage format: {key_part}")
                            except Exception as e:
                                logger.error(f"Failed to reverse video presigned URL to key in printable: {e}")
                    # External videos (youtube, vimeo, loom, spotify) - keep URL as-is, don't upload
                
                # Process ANIMATION elements - upload videoSrc to S3 (same as video but uses videoSrc field)
                elif el.get("type") == "animation" and "videoSrc" in el:
                    src = el["videoSrc"]
                    if src.startswith("data:video"):
                        try:
                            s3_uri = self.upload_base64_video(src, user_id, "printables", printable_id)
                            el["videoSrc"] = s3_uri
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                            logger.info(f"🎬 [PRINTABLE] Uploaded animation video to S3: {key}")
                        except Exception as e:
                            logger.error(f"Failed to process animation element in printable {printable_id}: {e}")
                            raise
                    elif src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        # Copy foreign media to this document's prefix
                        if self._is_foreign_key(key, user_id, "printables", printable_id):
                            new_uri = self._copy_foreign_media(key, user_id, "printables", printable_id)
                            el["videoSrc"] = new_uri
                            key = new_uri.replace(_S3_PREFIX, "")
                        active_keys.add(key)
                    elif src.startswith("http") and ".amazonaws.com/" in src:
                        # Convert presigned URL back to s3:// key
                        try:
                            clean_url = src.split("?")[0]
                            unique_code = get_user_id(user_id)
                            if unique_code in clean_url:
                                key_part = clean_url[clean_url.find(unique_code):]
                                # Copy foreign media to this document's prefix
                                if self._is_foreign_key(key_part, user_id, "printables", printable_id):
                                    new_uri = self._copy_foreign_media(key_part, user_id, "printables", printable_id)
                                    el["videoSrc"] = new_uri
                                    key_part = new_uri.replace(_S3_PREFIX, "")
                                else:
                                    el["videoSrc"] = f"{_S3_PREFIX}{key_part}"
                                active_keys.add(key_part)
                                logger.info(f"🔄 [PRINTABLE ANIMATION] Converted presigned URL back to storage format: {key_part}")
                        except Exception as e:
                            logger.error(f"Failed to reverse animation presigned URL to key in printable: {e}")

                updated_elements.append(el)
            
            PAGE["elements"] = updated_elements
            updated_PAGES.append(PAGE)

        return updated_PAGES, active_keys

    async def process_presentation_slides(self, slides: List[Dict[str, Any]], user_id: str, pres_id: str) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """
        Process slides JSON.
        Iterate elements, find type='image' or 'icon', process and upload to S3.
        Returns: (Updated Slides, Set of Active S3 Keys)
        """
        active_keys = set()
        updated_slides = []

        for slide in slides:
            elements = slide.get("elements", [])
            updated_elements = []
            
            for el in elements:
                # Process IMAGE elements
                if el.get("type") == "image" and "src" in el:
                    src = el["src"]
                    if src.startswith("data:image"):
                        try:
                            s3_uri = self.upload_base64_image(src, user_id, "presentations", pres_id)
                            el["src"] = s3_uri
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                        except Exception as e:
                            logger.error(f"Failed to process image element in presentation {pres_id}: {e}")
                            raise
                    elif src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        # Copy foreign media to this document's prefix
                        if self._is_foreign_key(key, user_id, "presentations", pres_id):
                            new_uri = self._copy_foreign_media(key, user_id, "presentations", pres_id)
                            el["src"] = new_uri
                            key = new_uri.replace(_S3_PREFIX, "")
                        active_keys.add(key)
                    elif src.startswith("http") and ".amazonaws.com/" in src:
                        # CRITICAL: Detect existing Presigned URL and convert back to s3:// key
                        try:
                            clean_url = src.split("?")[0]
                            unique_code = get_user_id(user_id)
                            if unique_code in clean_url:
                                key_part = clean_url[clean_url.find(unique_code):]
                                # Copy foreign media to this document's prefix
                                if self._is_foreign_key(key_part, user_id, "presentations", pres_id):
                                    new_uri = self._copy_foreign_media(key_part, user_id, "presentations", pres_id)
                                    el["src"] = new_uri
                                    key_part = new_uri.replace(_S3_PREFIX, "")
                                else:
                                    el["src"] = f"{_S3_PREFIX}{key_part}"
                                active_keys.add(key_part)
                                logger.info(f"🔄 Converted presigned URL back to storage format: {key_part}")
                        except Exception as e:
                            logger.error(f"Failed to reverse presigned URL to key: {e}")
                    elif src.startswith("http") and self._is_ephemeral_url(src):
                        # CRITICAL: External ephemeral URL (e.g. Runware CDN) – download and upload to S3
                        try:
                            s3_uri = await self.upload_url_image(src, user_id, "presentations", pres_id)
                            el["src"] = s3_uri
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                            logger.info(f"📥 [PRESENTATION] Migrated ephemeral URL to S3: {src[:80]}...")
                        except Exception as e:
                            logger.warning(f"⚠️ [PRESENTATION] Could not migrate ephemeral URL, keeping original: {e}")
                
                # Process ICON elements - upload SVG to S3 for consistency
                elif el.get("type") == "icon" and el.get("svgPath"):
                    svg_path = el["svgPath"]
                    icon_name = el.get("resolvedIconName") or el.get("iconName") or "icon"
                    fill_color = el.get("fill", "#ffffff")
                    svg_src = el.get("svgSrc", "")
                    
                    # Check if already has S3 URL
                    if svg_src.startswith(_S3_PREFIX):
                        key = svg_src.replace(_S3_PREFIX, "")
                        # Copy foreign media to this document's prefix
                        if self._is_foreign_key(key, user_id, "presentations", pres_id):
                            new_uri = self._copy_foreign_media(key, user_id, "presentations", pres_id)
                            el["svgSrc"] = new_uri
                            key = new_uri.replace(_S3_PREFIX, "")
                        active_keys.add(key)
                    elif svg_src.startswith("http") and ".amazonaws.com/" in svg_src:
                        # CRITICAL: Detect existing Presigned URL and convert back to s3:// key (skip re-upload)
                        try:
                            clean_url = svg_src.split("?")[0]
                            unique_code = get_user_id(user_id)
                            if unique_code in clean_url:
                                key_part = clean_url[clean_url.find(unique_code):]
                                # Copy foreign media to this document's prefix
                                if self._is_foreign_key(key_part, user_id, "presentations", pres_id):
                                    new_uri = self._copy_foreign_media(key_part, user_id, "presentations", pres_id)
                                    el["svgSrc"] = new_uri
                                    key_part = new_uri.replace(_S3_PREFIX, "")
                                else:
                                    el["svgSrc"] = f"{_S3_PREFIX}{key_part}"
                                active_keys.add(key_part)
                                logger.info(f"🔄 [ICON] Converted presigned URL back to storage format: {key_part}")
                        except Exception as e:
                            logger.error(f"Failed to reverse icon presigned URL to key: {e}")
                    else:
                        # Upload icon SVG to S3 (only for NEW icons)
                        try:
                            s3_uri = self.upload_svg_icon(svg_path, icon_name, user_id, "presentations", pres_id, fill_color)
                            el["svgSrc"] = s3_uri  # Store S3 URL for the SVG
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                        except Exception as e:
                            logger.error(f"Failed to upload icon {icon_name}: {e}")
                
                # Process VIDEO elements - upload to S3 (local uploads only, not external URLs)
                elif el.get("type") == "video" and "src" in el:
                    src = el["src"]
                    video_type = el.get("videoType", "local")
                    
                    # Only process local/recorded videos (base64), skip external URLs (youtube, vimeo, etc.)
                    if video_type in ["local", "recorded"] or src.startswith("data:video"):
                        if src.startswith("data:video"):
                            try:
                                s3_uri = self.upload_base64_video(src, user_id, "presentations", pres_id)
                                el["src"] = s3_uri
                                key = s3_uri.replace(_S3_PREFIX, "")
                                active_keys.add(key)
                                logger.info(f"🎬 [PRESENTATION] Uploaded video to S3: {key}")
                            except Exception as e:
                                logger.error(f"Failed to process video element in presentation {pres_id}: {e}")
                                raise
                        elif src.startswith(_S3_PREFIX):
                            key = src.replace(_S3_PREFIX, "")
                            # Copy foreign media to this document's prefix
                            if self._is_foreign_key(key, user_id, "presentations", pres_id):
                                new_uri = self._copy_foreign_media(key, user_id, "presentations", pres_id)
                                el["src"] = new_uri
                                key = new_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                        elif src.startswith("http") and ".amazonaws.com/" in src:
                            # Convert presigned URL back to s3:// key
                            try:
                                clean_url = src.split("?")[0]
                                unique_code = get_user_id(user_id)
                                if unique_code in clean_url:
                                    key_part = clean_url[clean_url.find(unique_code):]
                                    # Copy foreign media to this document's prefix
                                    if self._is_foreign_key(key_part, user_id, "presentations", pres_id):
                                        new_uri = self._copy_foreign_media(key_part, user_id, "presentations", pres_id)
                                        el["src"] = new_uri
                                        key_part = new_uri.replace(_S3_PREFIX, "")
                                    else:
                                        el["src"] = f"{_S3_PREFIX}{key_part}"
                                    active_keys.add(key_part)
                                    logger.info(f"🔄 [VIDEO] Converted presigned URL back to storage format: {key_part}")
                            except Exception as e:
                                logger.error(f"Failed to reverse video presigned URL to key: {e}")
                    # External videos (youtube, vimeo, loom, spotify) - keep URL as-is, don't upload
                
                # Process ANIMATION elements - upload videoSrc to S3 (same as video but uses videoSrc field)
                elif el.get("type") == "animation" and "videoSrc" in el:
                    src = el["videoSrc"]
                    if src.startswith("data:video"):
                        try:
                            s3_uri = self.upload_base64_video(src, user_id, "presentations", pres_id)
                            el["videoSrc"] = s3_uri
                            key = s3_uri.replace(_S3_PREFIX, "")
                            active_keys.add(key)
                            logger.info(f"🎬 [PRESENTATION] Uploaded animation video to S3: {key}")
                        except Exception as e:
                            logger.error(f"Failed to process animation element in presentation {pres_id}: {e}")
                            raise
                    elif src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        # Copy foreign media to this document's prefix
                        if self._is_foreign_key(key, user_id, "presentations", pres_id):
                            new_uri = self._copy_foreign_media(key, user_id, "presentations", pres_id)
                            el["videoSrc"] = new_uri
                            key = new_uri.replace(_S3_PREFIX, "")
                        active_keys.add(key)
                    elif src.startswith("http") and ".amazonaws.com/" in src:
                        # Convert presigned URL back to s3:// key
                        try:
                            clean_url = src.split("?")[0]
                            unique_code = get_user_id(user_id)
                            if unique_code in clean_url:
                                key_part = clean_url[clean_url.find(unique_code):]
                                # Copy foreign media to this document's prefix
                                if self._is_foreign_key(key_part, user_id, "presentations", pres_id):
                                    new_uri = self._copy_foreign_media(key_part, user_id, "presentations", pres_id)
                                    el["videoSrc"] = new_uri
                                    key_part = new_uri.replace(_S3_PREFIX, "")
                                else:
                                    el["videoSrc"] = f"{_S3_PREFIX}{key_part}"
                                active_keys.add(key_part)
                                logger.info(f"🔄 [PRESENTATION ANIMATION] Converted presigned URL back to storage format: {key_part}")
                        except Exception as e:
                            logger.error(f"Failed to reverse animation presigned URL to key in presentation: {e}")

                updated_elements.append(el)
            
            slide["elements"] = updated_elements
            updated_slides.append(slide)

        return updated_slides, active_keys

    def list_s3_files(self, prefix: str) -> List[str]:
        """List all files in an S3 prefix."""
        try:
            # s3_client doesn't have list_objects exposed as helper, access private?
            # bucket._get_client()
            bucket_name, _ = bucket.get_config()
            client = bucket._get_client()
            env_prefix = bucket.get_environment_prefix()
            
            full_prefix = f"{env_prefix}/{prefix}"
            
            keys = []
            paginator = client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket_name, Prefix=full_prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Remove env prefix to get logical key
                        key = obj['Key']
                        if key.startswith(f"{env_prefix}/"):
                            key = key[len(env_prefix)+1:]
                        keys.append(key)
            return keys
        except Exception as e:
            logger.error(f"Failed to list S3 files: {e}")
            return []

    def garbage_collect(self, user_id: str, doc_type: str, doc_id: str, active_keys: Set[str]):
        """
        Delete files in S3 that are NOT in active_keys.
        Handles images, videos, and icons folders.
        """
        unique_code = get_user_id(user_id)
        
        # Collect all keys from images, videos, and icons folders
        all_keys = []
        for folder in ["images", "videos", "icons"]:
            prefix = f"{unique_code}/{doc_type}/{doc_id}/{folder}/"
            folder_keys = self.list_s3_files(prefix)
            all_keys.extend(folder_keys)
        
        # SAFETY LOGGING: Log what we're about to do
        logger.info(f"🔍 [GC] Document: {doc_type}/{doc_id}")
        logger.info(f"🔍 [GC] All keys in S3 ({len(all_keys)}): {all_keys[:5]}{'...' if len(all_keys) > 5 else ''}")
        logger.info(f"🔍 [GC] Active keys ({len(active_keys)}): {list(active_keys)[:5]}{'...' if len(active_keys) > 5 else ''}")
        
        orphaned = [k for k in all_keys if k not in active_keys]
        logger.info(f"🔍 [GC] Orphaned keys to delete ({len(orphaned)}): {orphaned[:5]}{'...' if len(orphaned) > 5 else ''}")
        
        if len(active_keys) == 0 and len(all_keys) > 0:
            logger.warning(f"⚠️ [GC] SAFETY: active_keys is empty but S3 has {len(all_keys)} files. SKIPPING GC to prevent data loss!")
            return
        
        for key in orphaned:
            logger.info(f"🗑️ Garbage collecting unused media: {key}")
            bucket.delete_file(key)

    def delete_document_folder(self, user_id: str, doc_type: str, doc_id: str):
        """Delete all images for a document."""
        unique_code = get_user_id(user_id)
        prefix = f"{unique_code}/{doc_type}/{doc_id}/"
        keys = self.list_s3_files(prefix)
        for key in keys:
             bucket.delete_file(key)
        logger.info(f"🗑️ Deleted S3 folder for {doc_type}/{doc_id}")

    def inject_presigned_urls_report(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace s3:// URLs with Presigned URLs in HTML content."""
        s3_regex = re.compile(rf'src=(["\'])' + re.escape(_S3_PREFIX) + r'([^"\']+)\1')
        
        updated_pages = []
        for page in pages:
            content = page.get("content", "")
            if not content:
                updated_pages.append(page)
                continue
            
            # Track freshly generated URLs to skip in healing pass
            freshly_generated_urls = set()
                
            def replace_match(match):
                quote = match.group(1)
                key = match.group(2)
                try:
                    # Generate presigned URL (valid for 60 mins)
                    url = bucket.generate_download_url(key, 3600) 
                    freshly_generated_urls.add(url)  # Track this URL
                    return f"src={quote}{url}{quote}"
                except Exception:
                    return match.group(0)

            new_content = s3_regex.sub(replace_match, content)
            
            # HEAL: Also fix existing expired presigned URLs in DB
            # BUT skip URLs we just generated above
            presigned_regex = re.compile(r'src=(["\'])(https://[^"\']*\.amazonaws\.com/[^"\']*\?[^"\']*X-Amz-[^"\']+)\1')
            
            def heal_presigned(match):
                quote = match.group(1)
                url = match.group(2)
                
                # Skip if we just generated this URL
                if url in freshly_generated_urls:
                    return match.group(0)
                
                try:
                    clean_url = url.split("?")[0]
                    parts = clean_url.split(".amazonaws.com/")
                    if len(parts) > 1:
                        path = parts[1]
                        env_prefix = bucket.get_environment_prefix()
                        if path.startswith(f"{env_prefix}/"):
                            key = path[len(env_prefix)+1:]
                        else:
                            key = path
                        url = bucket.generate_download_url(key, 3600)
                        logger.info(f"🩹 [REPORT HEAL] Refreshed expired signed URL for key: {key}")
                        return f"src={quote}{url}{quote}"
                except Exception:
                    pass
                return match.group(0)
            
            new_content = presigned_regex.sub(heal_presigned, new_content)
            page["content"] = new_content
            updated_pages.append(page)
            
        return updated_pages

    def inject_presigned_urls_presentation(self, slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace s3:// URLs with Presigned URLs in Slide Elements (images and icons) and Background Image."""
        updated_slides = []
        for slide in slides:
            # Handle Slide Background Image
            if "backgroundImage" in slide:
                bg_src = slide["backgroundImage"]
                if bg_src and bg_src.startswith(_S3_PREFIX):
                    key = bg_src.replace(_S3_PREFIX, "")
                    try:
                        url = bucket.generate_download_url(key, 3600)
                        slide["backgroundImage"] = url
                    except Exception:
                        pass
                elif bg_src and bg_src.startswith("http") and "X-Amz-Signature" in bg_src:
                    # Heal expired presigned URL in background image
                    try:
                        clean_url = bg_src.split("?")[0]
                        parts = clean_url.split(".amazonaws.com/")
                        if len(parts) > 1:
                            path = parts[1]
                            env_prefix = bucket.get_environment_prefix()
                            if path.startswith(f"{env_prefix}/"):
                                key = path[len(env_prefix)+1:]
                            else:
                                key = path
                            url = bucket.generate_download_url(key, 3600)
                            slide["backgroundImage"] = url
                            logger.info(f"🩹 [HEAL] Refreshed expired signed URL for background image key: {key}")
                    except Exception:
                        pass

            elements = slide.get("elements", [])
            updated_elements = []
            for el in elements:
                # Handle IMAGE elements
                if el.get("type") == "image" and "src" in el:
                    src = el["src"]
                    if src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        try:
                            url = bucket.generate_download_url(key, 3600)
                            el["src"] = url
                        except Exception:
                            pass
                    elif src.startswith("http") and "X-Amz-Signature" in src:
                        # CRITICAL: Found an expired/signed URL stored in DB! Heal it on the fly.
                        try:
                            clean_url = src.split("?")[0]
                            parts = clean_url.split(".amazonaws.com/")
                            if len(parts) > 1:
                                path = parts[1]
                                env_prefix = bucket.get_environment_prefix()
                                if path.startswith(f"{env_prefix}/"):
                                    key = path[len(env_prefix)+1:]
                                else:
                                    key = path
                                url = bucket.generate_download_url(key, 3600)
                                el["src"] = url
                                logger.info(f"🩹 [HEAL] Refreshed expired signed URL for key: {key}")
                        except Exception as e:
                            pass
                
                # Handle ICON elements - inject presigned URL for svgSrc
                elif el.get("type") == "icon" and "svgSrc" in el:
                    svg_src = el["svgSrc"]
                    if svg_src.startswith(_S3_PREFIX):
                        key = svg_src.replace(_S3_PREFIX, "")
                        try:
                            url = bucket.generate_download_url(key, 3600)
                            el["svgSrc"] = url
                        except Exception:
                            pass
                
                # Handle VIDEO elements - inject presigned URL for src (local/recorded videos only)
                elif el.get("type") == "video" and "src" in el:
                    src = el["src"]
                    video_type = el.get("videoType", "local")
                    
                    # Only process local/recorded videos stored in S3, skip external URLs
                    if video_type in ["local", "recorded"] or src.startswith(_S3_PREFIX):
                        if src.startswith(_S3_PREFIX):
                            key = src.replace(_S3_PREFIX, "")
                            try:
                                url = bucket.generate_download_url(key, 3600)
                                el["src"] = url
                            except Exception:
                                pass
                        elif src.startswith("http") and "X-Amz-Signature" in src:
                            # Heal expired presigned URL for video
                            try:
                                clean_url = src.split("?")[0]
                                parts = clean_url.split(".amazonaws.com/")
                                if len(parts) > 1:
                                    path = parts[1]
                                    env_prefix = bucket.get_environment_prefix()
                                    if path.startswith(f"{env_prefix}/"):
                                        key = path[len(env_prefix)+1:]
                                    else:
                                        key = path
                                    url = bucket.generate_download_url(key, 3600)
                                    el["src"] = url
                                    logger.info(f"🩹 [VIDEO HEAL] Refreshed expired signed URL for video key: {key}")
                            except Exception:
                                pass
                
                # Handle ANIMATION elements - inject presigned URL for videoSrc
                elif el.get("type") == "animation" and "videoSrc" in el:
                    src = el["videoSrc"]
                    if src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        try:
                            url = bucket.generate_download_url(key, 3600)
                            el["videoSrc"] = url
                        except Exception:
                            pass
                    elif src.startswith("http") and "X-Amz-Signature" in src:
                        # Heal expired presigned URL for animation video
                        try:
                            clean_url = src.split("?")[0]
                            parts = clean_url.split(".amazonaws.com/")
                            if len(parts) > 1:
                                path = parts[1]
                                env_prefix = bucket.get_environment_prefix()
                                if path.startswith(f"{env_prefix}/"):
                                    key = path[len(env_prefix)+1:]
                                else:
                                    key = path
                                url = bucket.generate_download_url(key, 3600)
                                el["videoSrc"] = url
                                logger.info(f"🩹 [ANIMATION HEAL] Refreshed expired signed URL for animation key: {key}")
                        except Exception:
                            pass

                updated_elements.append(el)
            slide["elements"] = updated_elements
            updated_slides.append(slide)
        return updated_slides

    def inject_presigned_urls_printable(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace s3:// URLs with Presigned URLs in Printable Page Elements (images and icons) and Background Image."""
        updated_pages = []
        for page in pages:
            # Handle Page Background Image
            if "backgroundImage" in page:
                bg_src = page["backgroundImage"]
                if bg_src and bg_src.startswith(_S3_PREFIX):
                    key = bg_src.replace(_S3_PREFIX, "")
                    try:
                        url = bucket.generate_download_url(key, 3600)
                        page["backgroundImage"] = url
                    except Exception:
                        pass
                elif bg_src and bg_src.startswith("http") and "X-Amz-Signature" in bg_src:
                    # Heal expired presigned URL in background image
                    try:
                        clean_url = bg_src.split("?")[0]
                        parts = clean_url.split(".amazonaws.com/")
                        if len(parts) > 1:
                            path = parts[1]
                            env_prefix = bucket.get_environment_prefix()
                            if path.startswith(f"{env_prefix}/"):
                                key = path[len(env_prefix)+1:]
                            else:
                                key = path
                            url = bucket.generate_download_url(key, 3600)
                            page["backgroundImage"] = url
                            logger.info(f"🩹 [PRINTABLE HEAL] Refreshed expired signed URL for background image key: {key}")
                    except Exception:
                        pass

            elements = page.get("elements", [])
            updated_elements = []
            for el in elements:
                # Handle IMAGE elements
                if el.get("type") == "image" and "src" in el:
                    src = el["src"]
                    if src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        try:
                            url = bucket.generate_download_url(key, 3600)
                            el["src"] = url
                        except Exception:
                            pass
                    elif src.startswith("http") and "X-Amz-Signature" in src:
                        # CRITICAL: Found an expired/signed URL stored in DB! Heal it on the fly.
                        try:
                            clean_url = src.split("?")[0]
                            parts = clean_url.split(".amazonaws.com/")
                            if len(parts) > 1:
                                path = parts[1]
                                env_prefix = bucket.get_environment_prefix()
                                if path.startswith(f"{env_prefix}/"):
                                    key = path[len(env_prefix)+1:]
                                else:
                                    key = path
                                url = bucket.generate_download_url(key, 3600)
                                el["src"] = url
                                logger.info(f"🩹 [PRINTABLE HEAL] Refreshed expired signed URL for key: {key}")
                        except Exception as e:
                            pass
                
                # Handle ICON elements - inject presigned URL for svgSrc
                elif el.get("type") == "icon" and "svgSrc" in el:
                    svg_src = el["svgSrc"]
                    if svg_src.startswith(_S3_PREFIX):
                        key = svg_src.replace(_S3_PREFIX, "")
                        try:
                            url = bucket.generate_download_url(key, 3600)
                            el["svgSrc"] = url
                        except Exception:
                            pass
                
                # Handle VIDEO elements - inject presigned URL for src (local/recorded videos only)
                elif el.get("type") == "video" and "src" in el:
                    src = el["src"]
                    video_type = el.get("videoType", "local")
                    
                    # Only process local/recorded videos stored in S3, skip external URLs
                    if video_type in ["local", "recorded"] or src.startswith(_S3_PREFIX):
                        if src.startswith(_S3_PREFIX):
                            key = src.replace(_S3_PREFIX, "")
                            try:
                                url = bucket.generate_download_url(key, 3600)
                                el["src"] = url
                            except Exception:
                                pass
                        elif src.startswith("http") and "X-Amz-Signature" in src:
                            # Heal expired presigned URL for video
                            try:
                                clean_url = src.split("?")[0]
                                parts = clean_url.split(".amazonaws.com/")
                                if len(parts) > 1:
                                    path = parts[1]
                                    env_prefix = bucket.get_environment_prefix()
                                    if path.startswith(f"{env_prefix}/"):
                                        key = path[len(env_prefix)+1:]
                                    else:
                                        key = path
                                    url = bucket.generate_download_url(key, 3600)
                                    el["src"] = url
                                    logger.info(f"🩹 [PRINTABLE VIDEO HEAL] Refreshed expired signed URL for video key: {key}")
                            except Exception:
                                pass
                
                # Handle ANIMATION elements - inject presigned URL for videoSrc
                elif el.get("type") == "animation" and "videoSrc" in el:
                    src = el["videoSrc"]
                    if src.startswith(_S3_PREFIX):
                        key = src.replace(_S3_PREFIX, "")
                        try:
                            url = bucket.generate_download_url(key, 3600)
                            el["videoSrc"] = url
                        except Exception:
                            pass
                    elif src.startswith("http") and "X-Amz-Signature" in src:
                        # Heal expired presigned URL for animation video
                        try:
                            clean_url = src.split("?")[0]
                            parts = clean_url.split(".amazonaws.com/")
                            if len(parts) > 1:
                                path = parts[1]
                                env_prefix = bucket.get_environment_prefix()
                                if path.startswith(f"{env_prefix}/"):
                                    key = path[len(env_prefix)+1:]
                                else:
                                    key = path
                                url = bucket.generate_download_url(key, 3600)
                                el["videoSrc"] = url
                                logger.info(f"🩹 [PRINTABLE ANIMATION HEAL] Refreshed expired signed URL for animation key: {key}")
                        except Exception:
                            pass

                updated_elements.append(el)
            page["elements"] = updated_elements
            updated_pages.append(page)
        return updated_pages

    def generate_presigned_url(self, s3_uri_or_key: str, expiration: int = 3600) -> str:
        """
        Generate a presigned URL from an S3 URI or key.
        
        Args:
            s3_uri_or_key: Either 's3://citra-ai/key' or just 'key'
            expiration: URL expiration time in seconds (default 1 hour)
        
        Returns:
            Presigned HTTPS URL
        """
        # Extract key from s3:// URI if needed
        if s3_uri_or_key.startswith(_S3_PREFIX):
            key = s3_uri_or_key.replace(_S3_PREFIX, "")
        else:
            key = s3_uri_or_key
        
        return bucket.generate_download_url(key, expiration)

# Singleton instance
image_processor = ImageProcessor()
