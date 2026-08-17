#!/usr/bin/env python3
# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Optimized OCR Processor
======================

Efficiently processes documents in OCR path by:
1. Using PyMuPDF/local libraries for document structure
2. Using Vision API ONLY for actual text extraction from images/scanned content
3. Optimizing performance and reducing costs
"""

import fitz  # PyMuPDF
import logging
import asyncio
import os
import re
from typing import Dict, List, Optional, Any
from pathlib import Path
import time

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")
except ImportError:
    # dotenv not available, use system environment
    pass

# Import existing utilities
from text_extractors import extract_text_from_docx, extract_text_from_doc, extract_text_from_excel, extract_text_from_pptx
from vision_processor import extract_text_with_vision_api, extract_text_batch_with_vision_api

# Configuration
VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3-vl-32b-instruct")
llm_OCR_PROMPT = os.getenv(
    "llm_OCR_PROMPT",
    "Extract all readable text from this image. Return plain text only and preserve natural line breaks."
)
MAX_OCR_PAGES = int(os.getenv("MAX_OCR_PAGES", "100"))
OCR_RESOLUTION = float(os.getenv("OCR_RESOLUTION", "1"))  # Keep original resolution from environment
MAX_IMAGE_SIZE_MB = float(os.getenv("MAX_IMAGE_SIZE_MB", "5.0"))  # VRAM optimization limit
OCR_PAGE_DELAY = float(os.getenv("OCR_PAGE_DELAY", "0.5"))  # Delay between pages for VRAM cleanup
llm_OCR_BATCH_SIZE = int(os.getenv("llm_OCR_BATCH_SIZE", "5"))
llm_MAX_OUTPUT_TOKENS = int(os.getenv("llm_MAX_OUTPUT_TOKENS", "20000"))

logger = logging.getLogger(__name__)

class OptimizedOCRProcessor:
    """
    Optimized OCR processor that uses Vision API only for text extraction,
    not for document structure or page handling
    """
    
    def __init__(self):
        self.llm_model = VISION_MODEL
        self.llm_prompt = llm_OCR_PROMPT
        # Allow up to 100 pages per user request for large document processing
        self.max_ocr_pages = MAX_OCR_PAGES
        self.ocr_resolution = OCR_RESOLUTION
        self.max_image_size_mb = MAX_IMAGE_SIZE_MB
        self.ocr_page_delay = OCR_PAGE_DELAY
        self.llm_batch_size = max(1, llm_OCR_BATCH_SIZE)
        self.llm_max_output_tokens = llm_MAX_OUTPUT_TOKENS
        
        logger.info(f"🔧 OCR Processor Configuration:")
        logger.info(f"   - llm model: {self.llm_model}")
        logger.info(f"   - llm prompt preview: {self.llm_prompt[:80]}...")
        logger.info(f"   - Max OCR pages: {self.max_ocr_pages}")
        logger.info(f"   - OCR resolution: {self.ocr_resolution}x (maintains original quality)")
        logger.info(f"   - Max image size: {self.max_image_size_mb} MB")
        logger.info(f"   - Page processing delay: {self.ocr_page_delay}s")
        logger.info(f"   - llm batch size: {self.llm_batch_size} pages/request")
        logger.info(f"   - llm max output tokens: {self.llm_max_output_tokens}")
        
    async def process_document_with_ocr(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        ocr_options: Optional[Dict] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Process document with optimized OCR approach
        
        Args:
            file_content: Document file bytes
            filename: Original filename
            content_type: MIME content type
            ocr_options: Additional OCR processing options
            
        Returns:
            Dictionary with extracted text and metadata
        """
        start_time = time.time()
        file_ext = Path(filename).suffix.lower()
        
        logger.info(f"🚀 Starting optimized OCR processing for: {filename} ({file_ext})")
        
        try:
            # Route to appropriate processor based on file type
            if file_ext == '.pdf':
                result = await self._process_pdf_optimized(file_content, filename, ocr_options, progress_callback)
            elif file_ext in ['.docx', '.doc']:
                result = await self._process_word_optimized(file_content, filename, progress_callback)
            elif file_ext in ['.xlsx', '.xls']:
                result = await self._process_excel_optimized(file_content, filename, progress_callback)
            elif file_ext in ['.pptx', '.ppt']:
                result = await self._process_powerpoint_optimized(file_content, filename, progress_callback)
            elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                result = await self._process_image_optimized(file_content, filename, content_type, ocr_options, progress_callback)
            else:
                raise ValueError(f"Unsupported file type for OCR: {file_ext}")
            
            processing_time = time.time() - start_time
            result["metadata"]["processing_time"] = processing_time
            result["metadata"]["optimization_used"] = True
            
            logger.info(f"✅ Optimized OCR processing complete for {filename}: {processing_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ Optimized OCR processing failed for {filename}: {str(e)}")
            raise
    
    async def _process_pdf_optimized(
        self,
        file_content: bytes,
        filename: str,
        ocr_options: Optional[Dict] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Process PDF using PyMuPDF for structure + Vision API for ALL pages (OCR mode)
        When user chooses OCR, they want OCR for everything - no intelligence checks needed
        """
        logger.info(f"📄 Processing PDF with OCR for ALL pages: {filename}")
        
        try:
            # Step 1: Use PyMuPDF for document structure
            if progress_callback:
                progress_callback("analyzing", 30, "Analyzing PDF structure")
            
            doc = fitz.open(stream=file_content, filetype="pdf")
            total_pages = len(doc)
            
            logger.info(f"📊 PDF Analysis: {total_pages} pages detected - ALL will be OCR processed")

            if total_pages > self.max_ocr_pages:
                doc.close()
                message = (
                    f"PDF OCR is limited to {self.max_ocr_pages} pages. "
                    f"Received document has {total_pages} pages."
                )
                logger.error(message)
                limit = self.max_ocr_pages
                raise ValueError(
                    f"OCR currently supports PDF documents with {limit} pages or fewer. "
                    "Please split the file so each request stays within the limit and retry."
                )
            
            # Step 2: Process ALL pages with OCR (no intelligence - user wants OCR)
            if progress_callback:
                progress_callback("extracting", 40, f"Preparing {total_pages} pages for OCR processing")
            
            all_page_texts = []
            pages_for_ocr = []
            
            # Limit pages if configured
            max_pages = total_pages
            logger.info(f"🔍 Processing {max_pages} pages with OCR (limit: {self.max_ocr_pages})")
            
            for page_num in range(max_pages):
                page = doc.load_page(page_num)
                
                # Convert ALL pages to images for Vision API (user chose OCR)
                page_image = self._convert_page_to_image(page, page_num)
                pages_for_ocr.append({
                    'page_num': page_num,
                    'image_data': page_image
                })
                # Initialize with empty text
                all_page_texts.append("")
            
            # Step 3: Batch process ALL pages with OCR
            if progress_callback:
                progress_callback("extracting", 50, f"Processing {len(pages_for_ocr)} pages with Vision API")
            
            logger.info(f"🔍 OCR processing ALL {len(pages_for_ocr)} pages")
            ocr_results = await self._batch_process_ocr_pages(pages_for_ocr, filename, ocr_options, progress_callback)
            
            # Update page texts with OCR results
            if progress_callback:
                progress_callback("processing", 75, "Combining extracted text from all pages")
            
            for page_info in pages_for_ocr:
                page_num = page_info['page_num']
                ocr_text = ocr_results.get(page_num, "")
                all_page_texts[page_num] = ocr_text
            
            doc.close()
            
            # Step 4: Combine all OCR page texts
            if progress_callback:
                progress_callback("processing", 85, "Finalizing text extraction and cleanup")
            
            full_text = "\n\n".join(page_text for page_text in all_page_texts if page_text.strip())
            
            # No text cleanup needed - use raw extracted text
            
            # Create metadata
            metadata = {
                "filename": filename,
                "file_type": "pdf",
                "total_pages": total_pages,
                "pages_processed": len(all_page_texts),
                "ocr_pages": len(pages_for_ocr),
                "text_length": len(full_text),
                "vision_model": self.llm_model,
                "vision_api_used": True,
                "llm_vision_used": True,
                "llm_batch_size": self.llm_batch_size,
                "llm_max_output_tokens": self.llm_max_output_tokens,
                "user_requested_ocr": True
            }
            
            logger.info(f"📈 PDF OCR Processing Stats:")
            logger.info(f"   - Total pages: {total_pages}")
            logger.info(f"   - OCR processed: {len(pages_for_ocr)} pages")
            logger.info(f"   - Final text length: {len(full_text)} chars")
            
            return {
                "text": full_text,
                "metadata": metadata,
                "file_type": "pdf",
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ PDF OCR processing failed: {str(e)}")
            raise
    
    async def _process_word_optimized(
        self,
        file_content: bytes,
        filename: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Process Word document using local libraries - NO Vision API needed
        """
        logger.info(f"📝 Processing Word document with local extraction: {filename}")
        file_ext = Path(filename).suffix.lower()
        
        try:
            if progress_callback:
                progress_callback("extracting", 30, "Extracting text from Word document")
            
            # Use existing Word extraction (no Vision API)
            if file_ext == '.docx':
                text, metadata = extract_text_from_docx(file_content, filename)
            else:  # .doc
                text, metadata = extract_text_from_doc(file_content, filename)
            
            if progress_callback:
                progress_callback("processing", 80, "Finalizing text extraction")
            
            # No text cleanup needed - use raw extracted text
            
            # Update metadata
            metadata.update({
                "vision_api_used": False,
                "optimization_used": True,
                "text_length": len(text)
            })
            
            logger.info(f"✅ Word document processed locally: {len(text)} chars")
            
            return {
                "text": text,
                "metadata": metadata,
                "file_type": "word",
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ Word optimized processing failed: {str(e)}")
            raise
    
    async def _process_excel_optimized(
        self,
        file_content: bytes,
        filename: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Process Excel document using local libraries - NO Vision API needed
        """
        logger.info(f"📊 Processing Excel document with local extraction: {filename}")
        
        try:
            if progress_callback:
                progress_callback("extracting", 30, "Extracting text from Excel document")
            
            # Use existing Excel extraction (no Vision API)
            text, metadata = extract_text_from_excel(file_content, filename)
            
            if progress_callback:
                progress_callback("processing", 80, "Finalizing text extraction")
            
            # No text cleanup needed - use raw extracted text
            
            # Update metadata
            metadata.update({
                "vision_api_used": False,
                "optimization_used": True,
                "text_length": len(text)
            })
            
            logger.info(f"✅ Excel document processed locally: {len(text)} chars")
            
            return {
                "text": text,
                "metadata": metadata,
                "file_type": "excel",
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ Excel optimized processing failed: {str(e)}")
            raise
    
    async def _process_powerpoint_optimized(
        self,
        file_content: bytes,
        filename: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Process PowerPoint document using local libraries - NO Vision API needed
        """
        logger.info(f"📊 Processing PowerPoint document with local extraction: {filename}")
        
        try:
            if progress_callback:
                progress_callback("extracting", 30, "Extracting text from PowerPoint document")
            
            # Use existing PowerPoint extraction (no Vision API)
            text, metadata = extract_text_from_pptx(file_content, filename)
            
            if progress_callback:
                progress_callback("processing", 80, "Finalizing text extraction")
            
            # No text cleanup needed - use raw extracted text
            
            # Update metadata
            metadata.update({
                "vision_api_used": False,
                "optimization_used": True,
                "text_length": len(text)
            })
            
            logger.info(f"✅ PowerPoint document processed locally: {len(text)} chars")
            
            return {
                "text": text,
                "metadata": metadata,
                "file_type": "powerpoint",
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ PowerPoint optimized processing failed: {str(e)}")
            raise
    
    async def _process_image_optimized(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        ocr_options: Optional[Dict] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Process image using LLM Vision OCR (direct image processing)
        """
        logger.info(f"🖼️ Processing image with LLM Vision OCR: {filename}")
        
        try:
            # For pure images, call vision API directly
            if progress_callback:
                progress_callback("extracting", 40, "Processing image with LLM Vision OCR")
            
            vision_text = await self._extract_text_with_llm(
                file_content,
                filename,
                ocr_options
            )
            
            if progress_callback:
                progress_callback("processing", 80, "Finalizing text extraction")
            
            
            # No text cleanup needed - use raw extracted text
            
            metadata = {
                "filename": filename,
                "file_type": "image",
                "vision_model": self.llm_model,
                "vision_api_used": True,
                "llm_vision_used": True,
                "optimization_used": True,
                "text_length": len(vision_text)
            }
            
            logger.info(f"✅ Image processed with LLM Vision OCR: {len(vision_text)} chars")
            
            return {
                "text": vision_text,
                "metadata": metadata,
                "file_type": "image",
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ Image optimized processing failed: {str(e)}")
            raise
    
    def _convert_page_to_image(self, page, page_num: int) -> bytes:
        """
        Convert PDF page to image for Vision API processing at original resolution
        """
        try:
            # Use the configured OCR resolution; if it's 1, avoid creating/applying a Matrix (identity)
            if getattr(self, 'ocr_resolution', 1) == 1:
                # Native resolution
                pix = page.get_pixmap()
            else:
                mat = fitz.Matrix(self.ocr_resolution, self.ocr_resolution)
                pix = page.get_pixmap(matrix=mat)
            
            # Get image data
            img_data = pix.tobytes("png")
            image_size_mb = len(img_data) / (1024 * 1024)
            
            # Get page dimensions and content info
            page_rect = page.rect
            text_blocks = page.get_text_blocks()
            
            logger.info(f"🖼️ Page {page_num + 1} Image Conversion:")
            logger.info(f"   - Page size: {page_rect.width:.1f}x{page_rect.height:.1f}")
            if getattr(self, 'ocr_resolution', 1) == 1:
                logger.info("   - Resolution: native (1x)")
            else:
                logger.info(f"   - Resolution: {self.ocr_resolution}x{self.ocr_resolution}")
            logger.info(f"   - Image size: {image_size_mb:.2f} MB")
            logger.info(f"   - Text blocks found: {len(text_blocks)}")
            
            # Clean up pixmap
            pix = None
            
            # Log if page appears to have extractable text already
            direct_text = page.get_text().strip()
            if direct_text:
                logger.warning(f"   - Page has {len(direct_text)} chars of extractable text - OCR may not be needed")
                logger.debug(f"   - Sample text: {direct_text[:100]}...")
            else:
                logger.info(f"   - No extractable text found - OCR needed")
            
            logger.debug(f"Page {page_num + 1}: Converted to image ({image_size_mb:.2f} MB)")
            
            return img_data
            
        except Exception as e:
            logger.error(f"Page {page_num + 1}: Image conversion failed: {e}")
            raise
    
    async def _batch_process_ocr_pages(
        self,
        pages_for_ocr: List[Dict],
        document_id: str,
        ocr_options: Optional[Dict] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[int, str]:
        """Process OCR pages using LLM in parallel batches for maximum speed."""
        total_pages = len(pages_for_ocr)
        logger.info(
            "🔄 Processing %s pages with LLM Vision OCR (batch size %s, parallel processing)",
            total_pages,
            self.llm_batch_size
        )

        ocr_results: Dict[int, str] = {page_info["page_num"]: "" for page_info in pages_for_ocr}
        if total_pages == 0:
            return ocr_results

        total_batches = (total_pages + self.llm_batch_size - 1) // self.llm_batch_size
        
        # Prepare all batches upfront
        batches = []
        for batch_index in range(total_batches):
            batch_start = batch_index * self.llm_batch_size
            batch = pages_for_ocr[batch_start: batch_start + self.llm_batch_size]
            page_numbers = [page_info["page_num"] for page_info in batch]
            page_filenames = [f"{document_id}_page_{page_num + 1}.png" for page_num in page_numbers]

            custom_prompt = ocr_options.get("prompt") if ocr_options else None
            prompt = self._build_llm_batch_prompt(page_numbers, custom_prompt)
            image_payloads = [
                {
                    "file_content": page_info["image_data"],
                    "filename": filename
                }
                for page_info, filename in zip(batch, page_filenames)
            ]
            
            batches.append({
                'batch_index': batch_index,
                'batch': batch,
                'page_numbers': page_numbers,
                'page_filenames': page_filenames,
                'prompt': prompt,
                'image_payloads': image_payloads
            })
        
        # Process all batches in parallel
        logger.info(f"🚀 Starting parallel processing of {total_batches} batches")
        
        async def process_single_batch(batch_info):
            """Process a single batch and return results"""
            batch_index = batch_info['batch_index']
            page_numbers = batch_info['page_numbers']
            
            try:
                raw_response = await self._extract_batch_with_llm(
                    batch_info['image_payloads'],
                    batch_info['prompt']
                )
                parsed_results = self._parse_llm_batch_response(raw_response, page_numbers)
                logger.info(
                    "📦 llm batch %s/%s processed successfully (%s pages)",
                    batch_index + 1,
                    total_batches,
                    len(batch_info['batch'])
                )
                return parsed_results
            except Exception as batch_error:
                logger.error(
                    "❌ llm batch %s/%s failed: %s",
                    batch_index + 1,
                    total_batches,
                    batch_error
                )
                # Fallback to individual page processing
                parsed_results = {}
                for page_info, filename in zip(batch_info['batch'], batch_info['page_filenames']):
                    page_num = page_info["page_num"]
                    try:
                        fallback_text = await self._extract_text_with_llm(
                            page_info["image_data"],
                            filename
                        )
                        parsed_results[page_num] = fallback_text
                        logger.info(
                            "↩️ Fallback OCR succeeded for page %s (%s chars)",
                            page_num + 1,
                            len(fallback_text)
                        )
                    except Exception as fallback_error:
                        logger.error(
                            "⚠️ Fallback OCR failed for page %s: %s",
                            page_num + 1,
                            fallback_error
                        )
                        parsed_results[page_num] = ""
                return parsed_results
        
        # Execute all batches in parallel using asyncio.gather
        batch_results = await asyncio.gather(
            *[process_single_batch(batch_info) for batch_info in batches],
            return_exceptions=False  # Let exceptions be handled within process_single_batch
        )
        
        # Combine all results
        for parsed_results in batch_results:
            ocr_results.update(parsed_results)
        
        # Update progress to completion
        if progress_callback:
            progress_callback(
                "extracting",
                70,
                f"Processed all {total_batches} batches in parallel ({total_pages} pages total)"
            )

        successful_pages = len([text for text in ocr_results.values() if text.strip()])
        logger.info(
            "🎯 Vision OCR complete: %s/%s pages produced text using batch size %s (parallel processing)",
            successful_pages,
            total_pages,
            self.llm_batch_size
        )
        return ocr_results

    def _build_llm_batch_prompt(self, page_numbers: List[int], custom_instruction: Optional[str] = None) -> str:
        """Construct a deterministic prompt for batched Vision OCR."""
        extraction_instruction = custom_instruction if custom_instruction else "Extract all readable text from each page."
        
        lines = [
            "You will receive a batch of document page images.",
            extraction_instruction,
            "For each page, output text using EXACTLY the following format:",
            "<<<PAGE {page_number} START>>>",
            "<page text>",
            "<<<PAGE {page_number} END>>>",
            "Use the document page numbers provided below for {page_number} and preserve the page order.",
            "If a page contains no text, still output the START/END markers with nothing between them.",
            "Do not include any commentary outside of these markers."
        ]

        lines.append("Page mapping (image index -> document page number):")
        for index, page_num in enumerate(page_numbers, start=1):
            lines.append(f"- Image {index} corresponds to document page {page_num + 1}.")

        lines.append("Return the pages in ascending order by document page number.")
        return "\n".join(lines)

    async def _extract_batch_with_llm(
        self,
        image_payloads: List[Dict[str, Any]],
        prompt: str
    ) -> str:
        """Execute a batched Vision OCR call for the provided images."""
        return await extract_text_batch_with_vision_api(
            image_payloads=image_payloads,
            prompt=prompt,
            max_output_tokens=self.llm_max_output_tokens
        )

    def _parse_llm_batch_response(
        self,
        raw_text: str,
        page_numbers: List[int]
    ) -> Dict[int, str]:
        """Parse llm batch output into a mapping of page index to extracted text."""
        extracted: Dict[int, str] = {}
        expected_map = {page_num + 1: page_num for page_num in page_numbers}
        pattern = re.compile(
            r"<<<PAGE\s+(\d+)\s+START>>>\s*(.*?)\s*<<<PAGE\s+\1\s+END>>>",
            re.DOTALL | re.IGNORECASE
        )

        for match in pattern.finditer(raw_text or ""):
            try:
                page_label = int(match.group(1))
            except ValueError:
                continue
            mapped_page = expected_map.get(page_label)
            if mapped_page is None:
                continue
            extracted[mapped_page] = match.group(2).strip()

        for page_num in page_numbers:
            extracted.setdefault(page_num, "")

        if len(extracted) != len(page_numbers):
            missing = [num + 1 for num in page_numbers if not extracted.get(num)]
            if missing:
                logger.warning(
                    "⚠️ llm batch response missing explicit output for pages: %s",
                    ", ".join(str(num) for num in missing)
                )

        return extracted

    async def _extract_text_with_llm(self, image_data: bytes, filename: str, ocr_options: Optional[Dict] = None) -> str:
        """Delegate image OCR to the shared vision API helper."""
        return await extract_text_with_vision_api(
            file_content=image_data,
            filename=filename,
            content_type="image/png",
            use_ocr=True,
            ocr_options={
                "prompt": ocr_options.get("prompt") if ocr_options else self.llm_prompt,
                "max_output_tokens": self.llm_max_output_tokens
            }
        )

# Global instance
optimized_ocr_processor = OptimizedOCRProcessor()