# #!/usr/bin/env python3
# """
# Advanced Text Cleanup for Document Processing
# ============================================

# This module provides intelligent text cleanup functionality for PDF/Word documents
# before storing in Milvus. It removes OCR artifacts, junk text, and improves
# text quality for better RAG performance.

# Features:
# - OCR artifact removal
# - Junk text detection using spaCy NLP
# - Text quality assessment
# - Meaningless content filtering
# - Language detection and validation
# - Text structure normalization
# """

# import re
# import logging
# import string
# from typing import List, Dict, Tuple, Optional
# from collections import Counter
# import unicodedata

# # Optional spacy import - gracefully degrade if not available
# try:
#     import spacy
#     SPACY_AVAILABLE = True
# except ImportError:
#     spacy = None
#     SPACY_AVAILABLE = False

# # Configure logging
# logger = logging.getLogger(__name__)

# class TextCleaner:
#     """Advanced text cleanup using spaCy and linguistic analysis"""
    
#     def __init__(self):
#         """Initialize the text cleaner with spaCy model"""
#         self.logger = logging.getLogger(__name__)
        
#         # Load spaCy model (try multiple models)
#         self.nlp = None
        
#         if not SPACY_AVAILABLE:
#             self.logger.warning("⚠️ spaCy not available - using basic text cleanup without NLP features")
#             return
        
#         models_to_try = ['en_core_web_sm', 'en_core_web_md', 'en_core_web_lg']
        
#         for model_name in models_to_try:
#             try:
#                 self.nlp = spacy.load(model_name)
#                 self.logger.info(f"✅ Loaded spaCy model: {model_name}")
#                 break
#             except OSError:
#                 continue
        
#         if self.nlp is None:
#             self.logger.warning("⚠️ No spaCy model found. Installing en_core_web_sm...")
#             try:
#                 import subprocess
#                 subprocess.check_call(["python", "-m", "spacy", "download", "en_core_web_sm"])
#                 self.nlp = spacy.load("en_core_web_sm")
#                 self.logger.info("✅ Successfully installed and loaded en_core_web_sm")
#             except Exception as e:
#                 self.logger.error(f"❌ Failed to install spaCy model: {e}")
#                 self.nlp = None
        
#         # Text quality thresholds
#         self.MIN_WORD_LENGTH = 2
#         self.MIN_SENTENCE_LENGTH = 10
#         self.MIN_MEANINGFUL_WORDS_RATIO = 0.6
#         self.MAX_SPECIAL_CHARS_RATIO = 0.3
#         self.MIN_ALPHA_RATIO = 0.7
        
#         # OCR common error patterns
#         self.OCR_NOISE_PATTERNS = [
#             r'[|]{2,}',  # Multiple pipes
#             r'[.]{3,}',  # Multiple dots (scanning artifacts)
#             r'[_]{3,}',  # Multiple underscores
#             r'[*]{3,}',  # Multiple asterisks
#             r'[-]{4,}',  # Long dashes
#             r'[=]{3,}',  # Multiple equals
#             r'[~]{2,}',  # Multiple tildes
#             r'[\^]{2,}', # Multiple carets
#             r'[#]{2,}',  # Multiple hashes
#             r'[@]{2,}',  # Multiple at symbols
#             r'[%]{2,}',  # Multiple percent signs
#             r'[&]{2,}',  # Multiple ampersands
#             r'[+]{3,}',  # Multiple plus signs
#             r'[<>]{2,}', # Multiple angle brackets
#             r'[{}]{2,}', # Multiple curly braces
#             r'[\[\]]{2,}', # Multiple square brackets
#             r'[()]{3,}', # Multiple parentheses
#         ]
        
#         # Common OCR character confusions
#         self.OCR_CHAR_FIXES = {
#             '|': 'I',   # Pipe to I
#             '0': 'O',   # Zero to O (in words)
#             '1': 'l',   # One to l (in words)
#             '5': 'S',   # Five to S (in words)
#             '8': 'B',   # Eight to B (in words)
#             '6': 'G',   # Six to G (in words)
#             '°': 'o',   # Degree to o
#             '¢': 'c',   # Cent to c
#             '£': 'E',   # Pound to E
#         }
        
#         # Meaningless content indicators
#         self.JUNK_INDICATORS = [
#             'lorem ipsum',
#             'dummy text',
#             'placeholder',
#             'sample text',
#             'test data',
#             'confidential',
#             'do not distribute',
#             'draft version',
#             'internal use only',
#         ]
        
#         # Common header/footer patterns
#         self.HEADER_FOOTER_PATTERNS = [
#             r'page \d+ of \d+',
#             r'confidential and proprietary',
#             r'© \d{4}',
#             r'copyright \d{4}',
#             r'all rights reserved',
#             r'printed on \d{1,2}/\d{1,2}/\d{4}',
#             r'generated on \d{1,2}/\d{1,2}/\d{4}',
#             r'document version \d+\.\d+',
#         ]
    
#     def clean_extracted_text(self, text: str, document_id: str = "unknown") -> str:
#         """
#         Main cleanup function optimized for direct text extraction (99% of cases)
        
#         Args:
#             text: Raw extracted text from PDF/Word (usually clean, direct extraction)
#             document_id: Document ID for logging
            
#         Returns:
#             Lightly cleaned text with preserved semantic meaning and structure
#         """
#         if not text or not text.strip():
#             return ""
        
#         original_length = len(text)
#         self.logger.info(f"[{document_id}] 🧹 Starting gentle text cleanup for direct extraction - {original_length} chars")
        
#         # Check if text appears to be from direct extraction (clean) or OCR (artifacts)
#         is_likely_ocr = self._detect_ocr_artifacts(text)
        
#         if is_likely_ocr:
#             self.logger.info(f"[{document_id}] 🔍 OCR artifacts detected - applying comprehensive cleanup")
#             return self._clean_ocr_text(text, document_id)
#         else:
#             self.logger.info(f"[{document_id}] 📄 Clean direct extraction detected - applying gentle cleanup")
#             return self._clean_direct_text(text, document_id)

#     def _detect_ocr_artifacts(self, text: str) -> bool:
#         """
#         Detect if text contains OCR artifacts that need aggressive cleanup
#         Returns True if OCR artifacts are detected, False for clean direct text
#         """
#         if not text:
#             return False
        
#         # Count potential OCR indicators
#         ocr_indicators = 0
#         total_chars = len(text)
        
#         # Check for common OCR character substitutions
#         ocr_chars = text.count('|') + text.count('1') + text.count('0')
#         if ocr_chars > total_chars * 0.05:  # More than 5% OCR-like chars
#             ocr_indicators += 1
        
#         # Check for excessive punctuation artifacts
#         excessive_punctuation = len(re.findall(r'[.]{4,}|[_]{4,}|[=]{4,}|[*]{3,}', text))
#         if excessive_punctuation > 3:
#             ocr_indicators += 1
        
#         # Check for character substitution patterns
#         substitution_patterns = ['tlie', 'liave', 'witli', 'aiul', 'oi ', 'cau ', 'wlien']
#         substitution_count = sum(text.lower().count(pattern) for pattern in substitution_patterns)
#         if substitution_count > 2:
#             ocr_indicators += 1
        
#         # Check for unusual character sequences
#         unusual_sequences = len(re.findall(r'[^\w\s]{3,}', text))
#         if unusual_sequences > total_chars * 0.01:  # More than 1% unusual sequences
#             ocr_indicators += 1
        
#         # Threshold: 2 or more indicators suggest OCR text
#         return ocr_indicators >= 2

#     def _clean_direct_text(self, text: str, document_id: str) -> str:
#         """
#         Gentle cleanup for clean, directly extracted text - preserves semantic meaning
#         Only removes obvious artifacts while maintaining all content structure
#         """
#         original_length = len(text)
        
#         # Step 1: Very gentle Unicode normalization
#         cleaned_text = self._normalize_unicode(text)
        
#         # Step 2: Only remove obvious artifacts (very conservative)
#         cleaned_text = self._remove_obvious_artifacts_only(cleaned_text)
        
#         # Step 3: Minimal whitespace normalization (preserve structure)
#         cleaned_text = self._normalize_whitespace_minimal(cleaned_text)
        
#         # Step 4: Skip NLP filtering for direct text - preserve everything
#         # No spaCy processing to avoid breaking semantic meaning
        
#         # Step 5: Basic quality validation (not filtering)
#         quality_score = self.get_text_quality_score(cleaned_text)
        
#         final_length = len(cleaned_text)
#         reduction_ratio = (original_length - final_length) / original_length if original_length > 0 else 0
        
#         self.logger.info(f"[{document_id}] ✅ Gentle cleanup complete: {original_length} → {final_length} chars ({reduction_ratio:.1%} reduction, quality: {quality_score:.2f})")
        
#         return cleaned_text

#     def _clean_ocr_text(self, text: str, document_id: str) -> str:
#         """
#         Comprehensive cleanup for OCR text with artifacts - uses full spaCy processing
#         """
#         original_length = len(text)
#         self.logger.info(f"[{document_id}] 🔧 Applying comprehensive OCR cleanup")
        
#         # Full cleanup pipeline for OCR text
#         cleaned_text = self._normalize_unicode(text)
#         cleaned_text = self._remove_ocr_artifacts_gentle(cleaned_text)
#         cleaned_text = self._fix_ocr_character_errors_contextual(cleaned_text)
#         cleaned_text = self._normalize_whitespace_preserve_structure(cleaned_text)
#         cleaned_text = self._remove_headers_footers_semantic(cleaned_text)
        
#         # Apply NLP filtering only for OCR text
#         if self.nlp:
#             cleaned_text = self._filter_meaningful_content(cleaned_text, document_id)
#         else:
#             cleaned_text = self._basic_meaningful_filter(cleaned_text)
        
#         quality_score = self._is_meaningful_text_with_coherency(cleaned_text)
#         final_length = len(cleaned_text)
#         reduction_ratio = (original_length - final_length) / original_length if original_length > 0 else 0
        
#         self.logger.info(f"[{document_id}] ✅ OCR cleanup complete: {original_length} → {final_length} chars ({reduction_ratio:.1%} reduction, quality: {quality_score:.2f})")
        
#         return cleaned_text

#     def _remove_obvious_artifacts_only(self, text: str) -> str:
#         """
#         Remove only the most obvious artifacts while preserving all meaningful content
#         Very conservative approach for direct text extraction
#         """
#         # Only remove extreme artifact patterns that are clearly not content
#         extreme_patterns = [
#             r'[|]{5,}',     # 5+ pipes (clearly artifacts)
#             r'[.]{8,}',     # 8+ dots (clearly not ellipsis)
#             r'[_]{8,}',     # 8+ underscores (clearly artifacts)
#             r'[-]{10,}',    # 10+ dashes (clearly artifacts)
#             r'[=]{6,}',     # 6+ equals (clearly artifacts)
#             r'[@#%&*+]{3,}', # 3+ special chars together (clearly artifacts)
#         ]
        
#         for pattern in extreme_patterns:
#             text = re.sub(pattern, ' ', text)
        
#         # Remove isolated special characters that are clearly artifacts
#         # But be very conservative - only remove if surrounded by spaces
#         text = re.sub(r'\s[|@#%&*+=]{1}\s', ' ', text)
        
#         return text

#     def _normalize_whitespace_minimal(self, text: str) -> str:
#         """
#         Minimal whitespace normalization that preserves document structure
#         """
#         # Only fix the most obvious spacing issues
        
#         # Limit consecutive spaces to 2 (preserve some formatting)
#         text = re.sub(r'[ \t]{4,}', '  ', text)
        
#         # Limit consecutive newlines to 3 (preserve paragraph breaks)
#         text = re.sub(r'\n{5,}', '\n\n\n', text)
        
#         # Fix obvious punctuation spacing issues
#         text = re.sub(r'\.([A-Z])', r'. \1', text)  # Missing space after period
#         text = re.sub(r',([a-zA-Z])', r', \1', text)  # Missing space after comma
        
#         # Fix obvious broken words ONLY (very conservative)
#         # Only fix if it's clearly a hyphenated word break
#         text = re.sub(r'([a-z])-\s*\n\s*([a-z])', r'\1\2', text)
        
#         return text.strip()
    
#     def _normalize_unicode(self, text: str) -> str:
#         """Normalize Unicode characters"""
#         # Normalize Unicode to NFC form
#         text = unicodedata.normalize('NFC', text)
        
#         # Remove or replace problematic Unicode characters
#         text = text.replace('\ufeff', '')  # Remove BOM
#         text = text.replace('\u00a0', ' ')  # Non-breaking space to regular space
#         text = text.replace('\u2018', "'")  # Left single quote
#         text = text.replace('\u2019', "'")  # Right single quote
#         text = text.replace('\u201c', '"')  # Left double quote
#         text = text.replace('\u201d', '"')  # Right double quote
#         text = text.replace('\u2013', '-')  # En dash
#         text = text.replace('\u2014', '-')  # Em dash
#         text = text.replace('\u2026', '...')  # Ellipsis
        
#         return text
    
#     def _remove_ocr_artifacts_gentle(self, text: str) -> str:
#         """Gently remove OCR artifacts while preserving sentence structure"""
#         # More conservative pattern removal to preserve meaning
#         gentle_patterns = [
#             r'[|]{3,}',     # Only remove 3+ pipes (keep single/double for tables)
#             r'[.]{5,}',     # Only remove 5+ dots (keep ellipsis)
#             r'[_]{5,}',     # Only remove 5+ underscores
#             r'[-]{6,}',     # Only remove 6+ dashes (keep em-dash)
#             r'[=]{4,}',     # Only remove 4+ equals
#             r'[~]{3,}',     # Remove 3+ tildes
#             r'[@]{2,}',     # Remove 2+ at symbols
#             r'[%]{3,}',     # Remove 3+ percent signs
#             r'[&]{2,}',     # Remove 2+ ampersands
#             r'[+]{4,}',     # Remove 4+ plus signs
#         ]
        
#         # Apply gentle cleaning
#         for pattern in gentle_patterns:
#             text = re.sub(pattern, ' ', text)
        
#         # Remove excessive special character sequences but preserve some structure
#         text = re.sub(r'[^\w\s.-]{4,}', ' ', text)
        
#         # Remove standalone numbers that are clearly artifacts (not dates, years, etc.)
#         text = re.sub(r'\b\d{1,2}\b(?=\s+[A-Z]|\s*$)', ' ', text)  # Only single/double digits followed by capitals or end
        
#         return text

#     def _fix_ocr_character_errors_contextual(self, text: str) -> str:
#         """Fix OCR errors while considering word context to preserve meaning"""
#         # Enhanced word-level fixes with context awareness
#         contextual_fixes = {
#             # Common OCR errors with context
#             r'\btlie\b': 'the',
#             r'\bliave\b': 'have', 
#             r'\bwitli\b': 'with',
#             r'\btliis\b': 'this',
#             r'\baiul\b': 'and',
#             r'\boi\b(?=\s+[a-z])': 'of',  # 'oi' -> 'of' only if followed by lowercase
#             r'\bcau\b': 'can',
#             r'\bwlien\b': 'when',
#             r'\bfhe\b': 'the',
#             r'\brhe\b': 'the',
#             r'\bthc\b': 'the',
#             r'\bfirom\b': 'from',
#             r'\bii\b(?=\s+[a-z])': 'if',  # 'ii' -> 'if' only if followed by lowercase
#             r'\baii\b': 'an',
#             r'\bwlth\b': 'with',
#             r'\bthat\b': 'that',  # Sometimes gets garbled
#         }
        
#         # Apply contextual fixes
#         for pattern, replacement in contextual_fixes.items():
#             text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
#         # Character-level fixes that preserve word boundaries
#         char_fixes_safe = {
#             # Only fix obvious character confusions within words
#             r'([a-z])1([a-z])': r'\1l\2',  # 1 -> l within words
#             r'([a-z])0([a-z])': r'\1o\2',  # 0 -> o within words  
#             r'([A-Z])1([a-z])': r'\1l\2',  # Capital + 1 + lowercase
#         }
        
#         for pattern, replacement in char_fixes_safe.items():
#             text = re.sub(pattern, replacement, text)
        
#         return text

#     def _normalize_whitespace_preserve_structure(self, text: str) -> str:
#         """Normalize whitespace while preserving document structure"""
#         # Preserve paragraph breaks (double newlines)
#         text = re.sub(r'\n{4,}', '\n\n\n', text)  # Limit to triple newlines max
        
#         # Replace multiple spaces with single space (but preserve some formatting)
#         text = re.sub(r'[ \t]{3,}', '  ', text)  # Keep up to double spaces for formatting
        
#         # Fix broken words at line endings (more conservative hyphenation handling)
#         # Only fix obvious cases where lowercase follows hyphen+newline+lowercase
#         text = re.sub(r'([a-z])-\s*\n\s*([a-z])', r'\1\2', text)
        
#         # Join lines that are clearly part of the same sentence (more conservative)
#         # Only join if line ends with lowercase/comma and next starts with lowercase
#         text = re.sub(r'([a-z,])\n\s*([a-z])', r'\1 \2', text)
        
#         # Fix punctuation spacing (conservative)
#         text = re.sub(r'\.([A-Z])', r'. \1', text)  # Period + capital letter
#         text = re.sub(r',([a-zA-Z])', r', \1', text)  # Comma + letter
        
#         return text.strip()

#     def _remove_headers_footers_semantic(self, text: str) -> str:
#         """Remove headers and footers using semantic understanding"""
#         lines = text.split('\n')
#         cleaned_lines = []
        
#         for i, line in enumerate(lines):
#             line = line.strip()
#             if not line:
#                 cleaned_lines.append('')
#                 continue
            
#             # More intelligent header/footer detection
#             is_header_footer = False
#             line_lower = line.lower()
            
#             # Check against patterns
#             for pattern in self.HEADER_FOOTER_PATTERNS:
#                 if re.search(pattern, line_lower):
#                     is_header_footer = True
#                     break
            
#             if not is_header_footer:
#                 # Enhanced heuristics for headers/footers
                
#                 # Page numbers (but preserve in-text references)
#                 if (len(line) < 8 and line.isdigit() and 
#                     (i < 3 or i > len(lines) - 3)):  # Only at top/bottom of document
#                     is_header_footer = True
                
#                 # Very short lines with only numbers/special chars at document edges
#                 elif (len(line) < 10 and re.match(r'^[\d\s\-_=.]+$', line) and
#                       (i < 5 or i > len(lines) - 5)):
#                     is_header_footer = True
                
#                 # All caps short lines (likely headers, but preserve important ones)
#                 elif (line.isupper() and len(line) < 30 and len(line) > 5 and
#                       not any(keyword in line_lower for keyword in ['important', 'note', 'warning', 'caution'])):
#                     # Keep important ALL CAPS content
#                     pass
                
#             # Preserve meaningful content
#             if not is_header_footer:
#                 cleaned_lines.append(line)
        
#         return '\n'.join(cleaned_lines)

#     def _is_meaningful_text_with_coherency(self, text: str) -> float:
#         """
#         Enhanced text quality assessment that considers coherency and semantic meaning
#         Returns a quality score from 0.0 to 1.0
#         """
#         if not text or len(text.strip()) == 0:
#             return 0.0
        
#         try:
#             # Basic quality metrics
#             basic_score = self.get_text_quality_score(text)
            
#             # Additional coherency metrics
#             coherency_score = self._assess_text_coherency(text)
            
#             # Combine scores with weights
#             final_score = (basic_score * 0.7) + (coherency_score * 0.3)
            
#             return min(1.0, final_score)
            
#         except Exception as e:
#             self.logger.debug(f"Quality assessment with coherency failed: {e}")
#             return 0.5

#     def _assess_text_coherency(self, text: str) -> float:
#         """Assess text coherency using linguistic patterns"""
#         if not text:
#             return 0.0
        
#         try:
#             # Split into sentences
#             sentences = re.split(r'[.!?]+', text)
#             valid_sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
            
#             if len(valid_sentences) < 2:
#                 return 0.5
            
#             coherency_indicators = 0
#             total_checks = 0
            
#             # Check for transition words and coherence markers
#             transition_patterns = [
#                 r'\b(however|therefore|furthermore|moreover|additionally|consequently|thus|hence)\b',
#                 r'\b(in addition|as a result|for example|for instance|on the other hand)\b',
#                 r'\b(first|second|third|finally|lastly|next|then)\b',
#                 r'\b(this|that|these|those)\s+(shows?|indicates?|suggests?|means?|demonstrates?)\b',
#             ]
            
#             for sentence in valid_sentences:
#                 sentence_lower = sentence.lower()
#                 total_checks += 1
                
#                 # Check for transition words
#                 for pattern in transition_patterns:
#                     if re.search(pattern, sentence_lower):
#                         coherency_indicators += 1
#                         break
                
#                 # Check for pronoun references (indicates continuation)
#                 if re.search(r'\b(he|she|it|they|this|that|these|those|his|her|its|their)\b', sentence_lower):
#                     coherency_indicators += 0.5
            
#             # Calculate coherency score
#             if total_checks > 0:
#                 coherency_ratio = coherency_indicators / total_checks
#                 return min(1.0, coherency_ratio * 2)  # Scale up since good coherency is valuable
            
#             return 0.5
            
#         except Exception:
#             return 0.5
    
#     def _remove_ocr_artifacts(self, text: str) -> str:
#         """Remove common OCR artifacts and noise patterns (legacy method - now uses gentle approach)"""
#         return self._remove_ocr_artifacts_gentle(text)
    
#     def _fix_ocr_character_errors(self, text: str) -> str:
#         """Fix common OCR character recognition errors (legacy method - now uses contextual approach)"""
#         return self._fix_ocr_character_errors_contextual(text)
    
#     def _normalize_whitespace(self, text: str) -> str:
#         """Normalize whitespace and line breaks (legacy method - now preserves structure)"""
#         return self._normalize_whitespace_preserve_structure(text)
    
#     def _remove_headers_footers(self, text: str) -> str:
#         """Remove common header and footer patterns (legacy method - now uses semantic approach)"""
#         return self._remove_headers_footers_semantic(text)
    
#     def _is_meaningful_text(self, text: str) -> bool:
#         """Assess overall text quality (legacy method - now uses enhanced scoring)"""
#         quality_score = self._is_meaningful_text_with_coherency(text)
#         return quality_score >= 0.5
    
#     def _filter_meaningful_content(self, text: str, document_id: str) -> str:
#         """Use spaCy NLP to filter meaningful content while preserving sentence coherency"""
#         if not self.nlp:
#             return self._basic_meaningful_filter(text)
        
#         try:
#             # Process text with spaCy (handle large texts by chunking at sentence boundaries)
#             max_length = 800000  # Reduced to 800K for better performance
#             if len(text) > max_length:
#                 # Intelligent chunking at paragraph/sentence boundaries
#                 chunks = self._intelligent_text_chunking(text, max_length)
#                 meaningful_chunks = []
                
#                 for i, chunk in enumerate(chunks):
#                     self.logger.debug(f"[{document_id}] Processing text chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
#                     meaningful_chunk = self._process_text_chunk_preserve_coherency(chunk, document_id)
#                     if meaningful_chunk.strip():
#                         meaningful_chunks.append(meaningful_chunk)
                
#                 return '\n\n'.join(meaningful_chunks)
#             else:
#                 return self._process_text_chunk_preserve_coherency(text, document_id)
                
#         except Exception as e:
#             self.logger.warning(f"[{document_id}] spaCy processing failed: {e}, using basic filter")
#             return self._basic_meaningful_filter(text)
    
#     def _intelligent_text_chunking(self, text: str, max_length: int) -> List[str]:
#         """
#         Intelligently chunk text at paragraph and sentence boundaries to preserve meaning
#         """
#         chunks = []
#         current_chunk = ""
        
#         # First try to split at paragraph boundaries (double newlines)
#         paragraphs = text.split('\n\n')
        
#         for paragraph in paragraphs:
#             paragraph = paragraph.strip()
#             if not paragraph:
#                 continue
                
#             # If adding this paragraph would exceed limit, finalize current chunk
#             if len(current_chunk) + len(paragraph) + 2 > max_length and current_chunk:
#                 chunks.append(current_chunk)
#                 current_chunk = paragraph
#             else:
#                 if current_chunk:
#                     current_chunk += '\n\n' + paragraph
#                 else:
#                     current_chunk = paragraph
            
#             # If single paragraph is too long, split at sentence boundaries
#             if len(current_chunk) > max_length:
#                 # Use spaCy to split at sentence boundaries
#                 try:
#                     doc = self.nlp(current_chunk)
#                     sentences = [sent.text.strip() for sent in doc.sents]
                    
#                     # Reconstruct chunks from sentences
#                     if chunks and current_chunk != paragraph:
#                         # Remove the oversized paragraph from current_chunk
#                         current_chunk = current_chunk.replace('\n\n' + paragraph, '').replace(paragraph, '')
#                         if current_chunk.strip():
#                             chunks.append(current_chunk)
                    
#                     # Create new chunks from sentences
#                     sentence_chunk = ""
#                     for sentence in sentences:
#                         if len(sentence_chunk) + len(sentence) + 1 > max_length and sentence_chunk:
#                             chunks.append(sentence_chunk)
#                             sentence_chunk = sentence
#                         else:
#                             if sentence_chunk:
#                                 sentence_chunk += ' ' + sentence
#                             else:
#                                 sentence_chunk = sentence
                    
#                     current_chunk = sentence_chunk
                    
#                 except Exception as chunk_error:
#                     # Chunking failed - fail fast
#                     raise RuntimeError(f"Text chunking failed: {chunk_error}")
#                     while len(oversized) > max_length:
#                         split_point = max_length
#                         # Try to split at word boundary
#                         while split_point > max_length * 0.8 and not oversized[split_point].isspace():
#                             split_point -= 1
                        
#                         if split_point <= max_length * 0.8:
#                             split_point = max_length
                        
#                         chunks.append(oversized[:split_point])
#                         oversized = oversized[split_point:].lstrip()
                    
#                     current_chunk = oversized
        
#         # Add remaining content
#         if current_chunk.strip():
#             chunks.append(current_chunk)
        
#         return chunks

#     def _process_text_chunk_preserve_coherency(self, text: str, document_id: str) -> str:
#         """
#         Process a text chunk while preserving sentence coherency and semantic meaning
#         """
#         if not text.strip():
#             return ""
        
#         try:
#             doc = self.nlp(text)
            
#             # Group sentences into coherent paragraphs based on semantic similarity
#             coherent_paragraphs = self._group_sentences_semantically(doc)
            
#             # Filter paragraphs for meaningful content
#             meaningful_paragraphs = []
#             for paragraph_sentences in coherent_paragraphs:
#                 filtered_paragraph = self._filter_paragraph_preserve_meaning(paragraph_sentences)
#                 if filtered_paragraph:
#                     meaningful_paragraphs.append(filtered_paragraph)
            
#             return '\n\n'.join(meaningful_paragraphs)
            
#         except Exception as e:
#             self.logger.debug(f"[{document_id}] Coherency processing failed: {e}, using basic sentence filter")
#             return self._process_text_chunk(text)

#     def _group_sentences_semantically(self, doc) -> List[List]:
#         """
#         Group sentences into semantically coherent paragraphs
#         """
#         if not doc.sents:
#             return []
        
#         sentences = list(doc.sents)
#         if not sentences:
#             return []
        
#         paragraphs = []
#         current_paragraph = [sentences[0]]
        
#         for i in range(1, len(sentences)):
#             current_sent = sentences[i]
#             previous_sent = sentences[i-1]
            
#             # Check for semantic continuity
#             should_group = self._should_group_sentences(previous_sent, current_sent)
            
#             if should_group and len(' '.join([s.text for s in current_paragraph])) < 1000:
#                 current_paragraph.append(current_sent)
#             else:
#                 # Start new paragraph
#                 if current_paragraph:
#                     paragraphs.append(current_paragraph)
#                 current_paragraph = [current_sent]
        
#         # Add the last paragraph
#         if current_paragraph:
#             paragraphs.append(current_paragraph)
        
#         return paragraphs

#     def _should_group_sentences(self, sent1, sent2) -> bool:
#         """
#         Determine if two sentences should be grouped together based on semantic coherency
#         """
#         # Check for explicit paragraph breaks
#         sent1_text = sent1.text.strip()
#         sent2_text = sent2.text.strip()
        
#         # Don't group if there's a clear topic change
#         if (sent2_text.startswith(('However,', 'Nevertheless,', 'On the other hand,', 'In contrast,', 'Meanwhile,')) or
#             sent1_text.endswith(('.', '!', '?')) and sent2_text[0].isupper() and 
#             len(sent2_text.split()) > 8):  # Long sentence starting with capital likely new topic
#             return False
        
#         # Group if sentences share entities or similar vocabulary
#         sent1_entities = {ent.text.lower() for ent in sent1.ents}
#         sent2_entities = {ent.text.lower() for ent in sent2.ents}
        
#         # If sentences share named entities, likely coherent
#         if sent1_entities & sent2_entities:
#             return True
        
#         # Check for pronoun references (indicates continuity)
#         sent2_pronouns = {token.text.lower() for token in sent2 if token.pos_ == 'PRON'}
#         if sent2_pronouns & {'he', 'she', 'it', 'they', 'this', 'that', 'these', 'those', 'his', 'her', 'its', 'their'}:
#             return True
        
#         # Check for lexical similarity (shared important words)
#         sent1_keywords = {token.lemma_.lower() for token in sent1 
#                          if token.pos_ in ['NOUN', 'VERB', 'ADJ'] and not token.is_stop and len(token.text) > 2}
#         sent2_keywords = {token.lemma_.lower() for token in sent2 
#                          if token.pos_ in ['NOUN', 'VERB', 'ADJ'] and not token.is_stop and len(token.text) > 2}
        
#         if sent1_keywords and sent2_keywords:
#             overlap_ratio = len(sent1_keywords & sent2_keywords) / min(len(sent1_keywords), len(sent2_keywords))
#             if overlap_ratio > 0.3:  # 30% keyword overlap suggests coherency
#                 return True
        
#         # Default to grouping for short sentences (likely continuations)
#         if len(sent2_text) < 50:
#             return True
        
#         return False

#     def _filter_paragraph_preserve_meaning(self, paragraph_sentences: List) -> str:
#         """
#         Filter a paragraph while preserving semantic meaning and sentence relationships
#         """
#         if not paragraph_sentences:
#             return ""
        
#         meaningful_sentences = []
        
#         for sent in paragraph_sentences:
#             sentence_text = sent.text.strip()
            
#             # Enhanced meaningfulness check that preserves context
#             if self._is_meaningful_sentence_enhanced(sent, sentence_text, paragraph_sentences):
#                 meaningful_sentences.append(sentence_text)
#             else:
#                 # If sentence is not meaningful but short, check if it's connecting important sentences
#                 if (len(sentence_text) < 30 and 
#                     meaningful_sentences and 
#                     self._is_connecting_sentence(sent, paragraph_sentences)):
#                     meaningful_sentences.append(sentence_text)
        
#         # Ensure we don't break critical sentence relationships
#         filtered_text = ' '.join(meaningful_sentences)
        
#         # Post-process to ensure coherency
#         return self._ensure_paragraph_coherency(filtered_text)

#     def _is_meaningful_sentence_enhanced(self, sent_obj, sentence_text: str, context_sentences: List) -> bool:
#         """
#         Enhanced meaningfulness check that considers context and semantic relationships
#         """
#         # Basic length check
#         if len(sentence_text) < self.MIN_SENTENCE_LENGTH:
#             return False
        
#         # Check for junk indicators first
#         sentence_lower = sentence_text.lower()
#         for indicator in self.JUNK_INDICATORS:
#             if indicator in sentence_lower:
#                 return False
        
#         # Count meaningful content
#         meaningful_tokens = 0
#         total_tokens = 0
#         entities = []
#         important_pos = set()
        
#         for token in sent_obj:
#             if token.is_alpha and len(token.text) >= self.MIN_WORD_LENGTH:
#                 total_tokens += 1
                
#                 # Collect entities and important POS tags
#                 if token.ent_type_:
#                     entities.append(token.ent_type_)
                
#                 if token.pos_ in ['NOUN', 'VERB', 'ADJ', 'ADV', 'PROPN', 'NUM']:
#                     important_pos.add(token.pos_)
                
#                 # Consider token meaningful based on multiple criteria
#                 if (token.ent_type_ or  # Named entity
#                     token.pos_ in ['NOUN', 'VERB', 'ADJ', 'ADV', 'PROPN'] or  # Important POS
#                     (not token.is_stop and len(token.text) > 3) or  # Non-stop word with substance
#                     token.pos_ == 'NUM'):  # Numbers can be important
#                     meaningful_tokens += 1
        
#         if total_tokens == 0:
#             return False
        
#         # Calculate meaningful token ratio
#         meaningful_ratio = meaningful_tokens / total_tokens
        
#         # Lower threshold if sentence has entities or important content markers
#         min_ratio = self.MIN_MEANINGFUL_WORDS_RATIO
#         if entities or len(important_pos) >= 2:
#             min_ratio *= 0.8  # Reduce threshold by 20% for content-rich sentences
        
#         if meaningful_ratio < min_ratio:
#             # Check if this sentence provides context for surrounding meaningful sentences
#             if not self._provides_context_value(sent_obj, context_sentences):
#                 return False
        
#         # Check alphabetic character ratio
#         alpha_chars = sum(1 for c in sentence_text if c.isalpha())
#         total_chars = len(sentence_text)
#         alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
        
#         if alpha_ratio < self.MIN_ALPHA_RATIO:
#             return False
        
#         return True

#     def _provides_context_value(self, sent_obj, context_sentences: List) -> bool:
#         """
#         Check if a sentence provides important context even if it has low meaningful word ratio
#         """
#         sentence_text = sent_obj.text.strip()
        
#         # Short connecting phrases that maintain flow
#         connecting_patterns = [
#             r'^(however|therefore|furthermore|moreover|additionally|consequently|thus|hence),?\s',
#             r'^(in addition|as a result|for example|for instance|on the other hand),?\s',
#             r'^(first|second|third|finally|lastly|next|then),?\s',
#             r'\b(this|that|these|those)\s+(shows?|indicates?|suggests?|means?)\b',
#         ]
        
#         sentence_lower = sentence_text.lower()
#         for pattern in connecting_patterns:
#             if re.search(pattern, sentence_lower):
#                 return True
        
#         # Check if sentence contains references to previous content
#         pronouns = {token.text.lower() for token in sent_obj if token.pos_ == 'PRON'}
#         if pronouns & {'this', 'that', 'these', 'those', 'it', 'they'}:
#             return True
        
#         return False

#     def _is_connecting_sentence(self, sent_obj, paragraph_sentences: List) -> bool:
#         """
#         Check if a sentence serves as a connector between important sentences
#         """
#         sentence_text = sent_obj.text.strip().lower()
        
#         # Common transition words and phrases
#         transitions = [
#             'however', 'therefore', 'furthermore', 'moreover', 'additionally',
#             'consequently', 'thus', 'hence', 'in addition', 'as a result',
#             'for example', 'for instance', 'meanwhile', 'nevertheless'
#         ]
        
#         return any(transition in sentence_text for transition in transitions)

#     def _ensure_paragraph_coherency(self, text: str) -> str:
#         """
#         Ensure the filtered paragraph maintains coherency and readability
#         """
#         if not text.strip():
#             return ""
        
#         # Fix potential issues from filtering
#         text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
#         text = re.sub(r'([.!?])\s*([a-z])', r'\1 \2', text)  # Fix sentence spacing
#         text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Ensure proper sentence separation
        
#         # Ensure text ends properly
#         if text and not text[-1] in '.!?':
#             # Try to find the last complete sentence
#             last_sentence_end = max(text.rfind('.'), text.rfind('!'), text.rfind('?'))
#             if last_sentence_end > len(text) * 0.7:  # If last sentence marker is in the last 30%
#                 text = text[:last_sentence_end + 1]
#             else:
#                 text = text.rstrip() + '.'
        
#         return text.strip()

#     def _process_text_chunk(self, text: str) -> str:
#         """Process a single chunk of text with spaCy (backward compatibility)"""
#         doc = self.nlp(text)
#         meaningful_sentences = []
        
#         for sent in doc.sents:
#             sentence_text = sent.text.strip()
            
#             if self._is_meaningful_sentence(sent, sentence_text):
#                 meaningful_sentences.append(sentence_text)
        
#         return ' '.join(meaningful_sentences)
    
#     def _is_meaningful_sentence(self, sent_obj, sentence_text: str) -> bool:
#         """Determine if a sentence contains meaningful content using spaCy analysis"""
#         if len(sentence_text) < self.MIN_SENTENCE_LENGTH:
#             return False
        
#         # Count meaningful words
#         meaningful_words = 0
#         total_words = 0
        
#         for token in sent_obj:
#             if token.is_alpha and len(token.text) >= self.MIN_WORD_LENGTH:
#                 total_words += 1
                
#                 # Consider word meaningful if it's:
#                 # - A named entity
#                 # - A content word (noun, verb, adjective, adverb)
#                 # - Not a stop word (unless it's part of important phrase)
#                 if (token.ent_type_ or 
#                     token.pos_ in ['NOUN', 'VERB', 'ADJ', 'ADV', 'PROPN'] or
#                     (not token.is_stop and token.pos_ in ['NOUN', 'VERB'])):
#                     meaningful_words += 1
        
#         if total_words == 0:
#             return False
        
#         # Check meaningful words ratio
#         meaningful_ratio = meaningful_words / total_words
#         if meaningful_ratio < self.MIN_MEANINGFUL_WORDS_RATIO:
#             return False
        
#         # Check for junk indicators
#         sentence_lower = sentence_text.lower()
#         for indicator in self.JUNK_INDICATORS:
#             if indicator in sentence_lower:
#                 return False
        
#         # Check alphabetic character ratio
#         alpha_chars = sum(1 for c in sentence_text if c.isalpha())
#         total_chars = len(sentence_text)
#         alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
        
#         if alpha_ratio < self.MIN_ALPHA_RATIO:
#             return False
        
#         return True
    
#     def _basic_meaningful_filter(self, text: str) -> str:
#         """Basic meaningful content filter without spaCy - preserves sentence coherency"""
#         # Split into paragraphs first to preserve structure
#         paragraphs = text.split('\n\n')
#         meaningful_paragraphs = []
        
#         for paragraph in paragraphs:
#             paragraph = paragraph.strip()
#             if not paragraph:
#                 continue
            
#             # Split paragraph into sentences while preserving relationships
#             sentences = re.split(r'(?<=[.!?])\s+', paragraph)
#             meaningful_sentences = []
            
#             for i, sentence in enumerate(sentences):
#                 sentence = sentence.strip()
#                 if len(sentence) < self.MIN_SENTENCE_LENGTH:
#                     # Check if it's a short connecting sentence
#                     if (meaningful_sentences and i < len(sentences) - 1 and
#                         self._is_short_connector(sentence)):
#                         meaningful_sentences.append(sentence)
#                     continue
                
#                 # Basic quality checks
#                 words = sentence.split()
#                 if len(words) < 3:  # Too short
#                     continue
                
#                 # Check alphabetic ratio
#                 alpha_chars = sum(1 for c in sentence if c.isalpha())
#                 total_chars = len(sentence)
#                 alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
                
#                 if alpha_ratio < self.MIN_ALPHA_RATIO:
#                     continue
                
#                 # Check for junk indicators
#                 sentence_lower = sentence.lower()
#                 has_junk = any(indicator in sentence_lower for indicator in self.JUNK_INDICATORS)
#                 if has_junk:
#                     continue
                
#                 # Check for meaningful content (nouns, verbs, etc.)
#                 content_words = 0
#                 for word in words:
#                     clean_word = word.strip(string.punctuation).lower()
#                     if (len(clean_word) > 2 and 
#                         clean_word not in {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'}):
#                         content_words += 1
                
#                 # Require at least 30% content words
#                 if content_words / len(words) >= 0.3:
#                     meaningful_sentences.append(sentence)
            
#             # Join sentences in paragraph, preserving natural flow
#             if meaningful_sentences:
#                 paragraph_text = '. '.join(meaningful_sentences)
#                 # Ensure proper punctuation
#                 if not paragraph_text.endswith(('.', '!', '?')):
#                     paragraph_text += '.'
#                 meaningful_paragraphs.append(paragraph_text)
        
#         return '\n\n'.join(meaningful_paragraphs)

#     def _is_short_connector(self, sentence: str) -> bool:
#         """Check if a short sentence is a meaningful connector"""
#         sentence_lower = sentence.lower().strip()
#         connectors = [
#             'however', 'therefore', 'furthermore', 'moreover', 'additionally',
#             'consequently', 'thus', 'hence', 'meanwhile', 'nevertheless',
#             'in addition', 'as a result', 'for example', 'for instance'
#         ]
#         return any(connector in sentence_lower for connector in connectors)
    
#     def _is_meaningful_text(self, text: str) -> bool:
#         """Assess overall text quality"""
#         if not text or len(text.strip()) < 20:
#             return False
        
#         # Check character composition
#         alpha_chars = sum(1 for c in text if c.isalpha())
#         digit_chars = sum(1 for c in text if c.isdigit())
#         space_chars = sum(1 for c in text if c.isspace())
#         special_chars = len(text) - alpha_chars - digit_chars - space_chars
        
#         total_chars = len(text)
        
#         # Calculate ratios
#         alpha_ratio = alpha_chars / total_chars
#         special_ratio = special_chars / total_chars
        
#         # Quality thresholds
#         if alpha_ratio < 0.6:  # Less than 60% alphabetic
#             return False
        
#         if special_ratio > 0.3:  # More than 30% special characters
#             return False
        
#         # Check for minimum word count
#         words = text.split()
#         meaningful_words = [w for w in words if len(w) >= 2 and w.isalpha()]
        
#         if len(meaningful_words) < 5:
#             return False
        
#         return True
    
#     def get_text_quality_score(self, text: str) -> float:
#         """
#         Calculate a quality score for the text (0.0 to 1.0)
        
#         Returns:
#             Quality score where 1.0 is highest quality
#         """
#         if not text or len(text.strip()) == 0:
#             return 0.0
        
#         try:
#             # Character composition analysis
#             total_chars = len(text)
#             alpha_chars = sum(1 for c in text if c.isalpha())
#             digit_chars = sum(1 for c in text if c.isdigit())
#             space_chars = sum(1 for c in text if c.isspace())
#             special_chars = total_chars - alpha_chars - digit_chars - space_chars
            
#             # Calculate ratios
#             alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
#             special_ratio = special_chars / total_chars if total_chars > 0 else 0
            
#             # Word analysis
#             words = text.split()
#             if not words:
#                 return 0.1
            
#             meaningful_words = [w for w in words if len(w) >= 2 and w.isalpha()]
#             word_quality = len(meaningful_words) / len(words) if words else 0
            
#             # Sentence structure analysis
#             sentences = re.split(r'[.!?]+', text)
#             valid_sentences = [s for s in sentences if len(s.strip()) > 10]
#             sentence_quality = len(valid_sentences) / len(sentences) if sentences else 0
            
#             # Check for OCR artifacts
#             ocr_penalty = 0
#             for pattern in self.OCR_NOISE_PATTERNS:
#                 matches = re.findall(pattern, text)
#                 ocr_penalty += len(matches) * 0.05  # 5% penalty per artifact
            
#             # Base quality score
#             quality_score = (
#                 alpha_ratio * 0.3 +
#                 word_quality * 0.3 +
#                 sentence_quality * 0.2 +
#                 (1 - special_ratio) * 0.2
#             )
            
#             # Apply penalties
#             quality_score = max(0.0, quality_score - ocr_penalty)
            
#             return min(1.0, quality_score)
            
#         except Exception as e:
#             logger.debug(f"Quality assessment failed: {e}")
#             return 0.5  # Default moderate score if assessment fails

#     def smart_clean_extracted_text(self, text: str, document_id: str = "unknown") -> str:
#         """
#         Smart text cleaning that only applies spaCy when junk characters are actually detected.
#         For direct text extraction (99% of cases), this preserves semantic meaning by avoiding
#         unnecessary processing when text is already clean.
        
#         Args:
#             text: Raw extracted text from PDF/Word
#             document_id: Document ID for logging
            
#         Returns:
#             Original text if clean, or cleaned text if junk detected
#         """
#         if not text or not text.strip():
#             return ""
        
#         original_length = len(text)
#         self.logger.info(f"[{document_id}] 🔍 Smart cleanup analysis starting - {original_length} chars")
        
#         # Step 1: Extract first 5 pages (or all content if less than 5 pages) for junk detection
#         sample_text = self._extract_sample_for_analysis(text, document_id)
        
#         # Step 2: Detect if sample contains junk characters that need cleanup
#         junk_detected, junk_score, junk_details = self._detect_junk_characters(sample_text, document_id)
        
#         if not junk_detected:
#             # No junk detected - return original text to preserve semantic meaning
#             self.logger.info(f"[{document_id}] ✅ Clean text detected (junk score: {junk_score:.3f}) - no processing needed")
#             return text
        
#         # Junk detected - apply gentle spaCy cleanup while preserving semantic meaning
#         self.logger.info(f"[{document_id}] ⚠️ Junk detected (score: {junk_score:.3f}) - applying gentle cleanup")
#         self.logger.info(f"[{document_id}] 📋 Junk details: {junk_details}")
        
#         # Apply conservative cleanup that preserves semantic meaning
#         cleaned_text = self._apply_gentle_cleanup_preserve_meaning(text, document_id, junk_details)
        
#         final_length = len(cleaned_text)
#         reduction_ratio = (original_length - final_length) / original_length if original_length > 0 else 0
        
#         # Verify we haven't damaged the text
#         if final_length < original_length * 0.80:  # If we removed more than 20%, be cautious
#             self.logger.warning(f"[{document_id}] ⚠️ Significant text reduction ({reduction_ratio:.1%}) - reverting to original")
#             return text
        
#         self.logger.info(f"[{document_id}] ✅ Gentle cleanup complete: {original_length} → {final_length} chars ({reduction_ratio:.1%} reduction)")
        
#         return cleaned_text

#     def _extract_sample_for_analysis(self, text: str, document_id: str) -> str:
#         """
#         Extract first 5 pages or equivalent content for junk detection analysis.
#         Aligned with direct text extraction from PyMuPDF, python-docx, and pandas.
#         """
#         # Direct text extraction creates page markers like "=== PAGE 1 ==="
#         # Look for these actual page markers from text_extractors.py
#         page_pattern = r'=== PAGE (\d+) ==='
#         page_matches = list(re.finditer(page_pattern, text))
        
#         if len(page_matches) >= 5:
#             # Extract content from pages 1-5 using actual extraction format
#             page_5_match = page_matches[4]  # 5th page (0-indexed)
#             # Find the start of page 6 or end of text
#             if len(page_matches) > 5:
#                 page_6_match = page_matches[5]
#                 sample_text = text[:page_6_match.start()]
#             else:
#                 sample_text = text
            
#             self.logger.debug(f"[{document_id}] 📄 Extracted first 5 pages for analysis ({len(sample_text)} chars)")
            
#         elif page_matches:
#             # Less than 5 pages - use all content
#             sample_text = text
#             self.logger.debug(f"[{document_id}] 📄 Document has {len(page_matches)} pages - analyzing all content")
            
#         else:
#             # No page markers - check for section markers from Word/Excel extraction
#             section_pattern = r'=== ([A-Z_]+) ==='
#             section_matches = list(re.finditer(section_pattern, text))
            
#             if section_matches and len(section_matches) >= 3:
#                 # For documents with sections (Word/Excel), take first 3 sections
#                 section_3_match = section_matches[2]  # 3rd section
#                 if len(section_matches) > 3:
#                     section_4_match = section_matches[3]
#                     sample_text = text[:section_4_match.start()]
#                 else:
#                     sample_text = text
#                 self.logger.debug(f"[{document_id}] 📄 Document has sections - analyzing first 3 sections ({len(sample_text)} chars)")
#             else:
#                 # No page or section markers - use first ~20% or max 10,000 chars for analysis
#                 # This handles plain text files or files without clear structure
#                 max_sample = min(len(text), max(int(len(text) * 0.2), 10000))
#                 sample_text = text[:max_sample]
#                 self.logger.debug(f"[{document_id}] 📄 No structure markers - analyzing first {len(sample_text)} chars (direct text extraction)")
        
#         return sample_text

#     def _detect_junk_characters(self, sample_text: str, document_id: str) -> Tuple[bool, float, Dict]:
#         """
#         Detect if sample text contains junk characters that need cleanup.
        
#         Returns:
#             Tuple of (junk_detected: bool, junk_score: float, details: dict)
#         """
#         if not sample_text.strip():
#             return False, 0.0, {}
        
#         total_chars = len(sample_text)
#         junk_indicators = {
#             'excessive_special_chars': 0,
#             'ocr_noise_patterns': 0,
#             'broken_words': 0,
#             'garbled_text': 0,
#             'unicode_artifacts': 0
#         }
        
#         # 1. Check for excessive special character sequences (OCR artifacts)
#         # Find all special character sequences but exclude our extraction markers
#         special_sequences = re.findall(r'[^\w\s]{3,}', sample_text)
#         excessive_special = 0
#         for seq in special_sequences:
#             # Skip if it's our extraction marker pattern (=== or similar)
#             if seq.startswith('===') and seq.endswith('==='):
#                 continue
#             excessive_special += 1
#         junk_indicators['excessive_special_chars'] = excessive_special
        
#         # 2. Check for OCR noise patterns
#         noise_patterns = [
#             r'[|]{2,}',     # Multiple pipes
#             r'[.]{4,}',     # Excessive dots
#             r'[_]{4,}',     # Multiple underscores
#             r'[-]{5,}',     # Long dashes
#             r'[~]{2,}',     # Multiple tildes
#             r'[@#%&+]{2,}', # Multiple symbols
#         ]
        
#         # Check for multiple equals but exclude our extraction markers
#         # First, exclude our extraction markers completely
#         text_without_markers = re.sub(r'=== (PAGE \d+|TABLE_\d+|SHEET_\d+|[A-Z_]+) ===', '', sample_text)
        
#         # Now count equals patterns in the remaining text
#         equals_matches = re.findall(r'[=]{3,}', text_without_markers)
#         noise_equals = len(equals_matches)
        
#         for pattern in noise_patterns:
#             matches = len(re.findall(pattern, sample_text))
#             junk_indicators['ocr_noise_patterns'] += matches
        
#         # Add the filtered equals count
#         junk_indicators['ocr_noise_patterns'] += noise_equals
        
#         # 3. Check for broken words (direct extraction errors, not OCR-specific)
#         # Be extremely conservative - only flag obvious extraction errors
#         broken_word_patterns = [
#             r'\b[a-z]{1,2}[0-9][a-z]{1,2}\b',  # Letters mixed with numbers like "w0rd" or "h3lp" 
#             r'\b[a-z]+[|][a-z]+\b',            # Words split by pipes from table extraction
#             r'\b[a-z]+1[a-z]+\b',              # Number 1 in middle of words like "word1ike"
#             r'\b[a-z]+0[a-z]+\b',              # Number 0 in middle of words like "c0mpared"
#         ]
        
#         for pattern in broken_word_patterns:
#             matches = len(re.findall(pattern, sample_text, re.IGNORECASE))
#             junk_indicators['broken_words'] += matches
        
#         # 4. Check for garbled text (nonsense character sequences) - very conservative
#         garbled_patterns = [
#             r'\b[bcdfghjklmnpqrstvwxyz]{6,}\b',  # Very long consonant sequences (6+ chars)
#             r'\b[aeiou]{5,}\b',                  # Very long vowel sequences (5+ chars)
#             r'\b[qxz]{3,}\b',                    # Multiple unusual letters
#         ]
        
#         for pattern in garbled_patterns:
#             matches = len(re.findall(pattern, sample_text, re.IGNORECASE))
#             junk_indicators['garbled_text'] += matches
        
#         # 5. Check for Unicode artifacts
#         unicode_artifacts = 0
#         problematic_unicode = ['\ufffd', '\u00a0', '\u2018', '\u2019', '\u201c', '\u201d']
#         for char in problematic_unicode:
#             unicode_artifacts += sample_text.count(char)
#         junk_indicators['unicode_artifacts'] = unicode_artifacts
        
#         # Calculate junk score (normalized by text length)
#         total_junk_items = sum(junk_indicators.values())
        
#         # Normalize by text length and word count
#         words = len(sample_text.split())
#         if words > 0:
#             junk_score = total_junk_items / words  # Junk items per word
#         else:
#             junk_score = 0.0
        
#         # Determine if cleanup is needed
#         # Threshold: more than 0.05 junk items per word (5 junk items per 100 words)
#         junk_threshold = 0.05
#         junk_detected = junk_score > junk_threshold
        
#         details = {
#             'junk_score': junk_score,
#             'threshold': junk_threshold,
#             'total_junk_items': total_junk_items,
#             'word_count': words,
#             'breakdown': junk_indicators
#         }
        
#         self.logger.debug(f"[{document_id}] 🔍 Junk analysis: score={junk_score:.4f}, threshold={junk_threshold:.4f}")
        
#         return junk_detected, junk_score, details

#     def _apply_gentle_cleanup_preserve_meaning(self, text: str, document_id: str, junk_details: Dict) -> str:
#         """
#         Apply very gentle cleanup that preserves semantic meaning while removing detected junk
#         """
#         self.logger.info(f"[{document_id}] 🧹 Applying gentle cleanup while preserving semantic meaning")
        
#         # Step 1: Conservative Unicode normalization
#         cleaned_text = self._normalize_unicode(text)
        
#         # Step 2: Remove only the most obvious OCR artifacts based on detection
#         if junk_details['breakdown']['ocr_noise_patterns'] > 0:
#             cleaned_text = self._remove_obvious_artifacts_only(cleaned_text)
        
#         # Step 3: Fix only obvious character errors (very conservative)
#         if junk_details['breakdown']['broken_words'] > 0:
#             cleaned_text = self._fix_obvious_character_errors_only(cleaned_text)
        
#         # Step 4: Gentle whitespace normalization (preserve structure)
#         cleaned_text = self._normalize_whitespace_preserve_structure(cleaned_text)
        
#         # Step 5: Apply spaCy filtering only if really needed and with maximum coherency preservation
#         if junk_details['junk_score'] > 0.1:  # Higher threshold for spaCy processing
#             if self.nlp:
#                 self.logger.info(f"[{document_id}] 🧠 Applying spaCy semantic filtering (high junk score: {junk_details['junk_score']:.3f})")
#                 cleaned_text = self._apply_minimal_spacy_filtering(cleaned_text, document_id)
#             else:
#                 self.logger.info(f"[{document_id}] 📝 spaCy unavailable - using basic semantic preservation")
#                 cleaned_text = self._basic_semantic_preserving_filter(cleaned_text)
        
#         return cleaned_text

#     def _remove_obvious_artifacts_only(self, text: str) -> str:
#         """Remove only the most obvious extraction artifacts without damaging content"""
#         # Very conservative artifact removal - only patterns that are clearly not content
#         # Aligned with direct text extraction artifacts (not OCR-specific)
#         obvious_artifacts = [
#             r'[|]{3,}',      # 3+ pipes definitely artifacts (table extraction issues)
#             r'[.]{6,}',      # 6+ dots definitely artifacts (formatting remnants)
#             r'[_]{6,}',      # 6+ underscores definitely artifacts (table borders)
#             r'[-]{8,}',      # 8+ dashes definitely artifacts (section separators)
#             r'[@#%&+]{3,}',  # 3+ special symbols definitely artifacts
#             r'\s{6,}',       # 6+ consecutive spaces (formatting artifacts from direct extraction)
#         ]
        
#         for pattern in obvious_artifacts:
#             text = re.sub(pattern, ' ', text)
        
#         # Handle equals separately to preserve our extraction markers
#         equals_matches = list(re.finditer(r'[=]{5,}', text))
#         for match in reversed(equals_matches):  # Process in reverse to maintain positions
#             match_text = match.group()
#             context_start = max(0, match.start() - 10)
#             context_end = min(len(text), match.end() + 10)
#             context = text[context_start:context_end]
            
#             # Only remove if it's NOT our extraction marker
#             if not re.search(r'=== (PAGE \d+|[A-Z_]+) ===', context):
#                 text = text[:match.start()] + ' ' + text[match.end():]
        
#         # Remove standalone formatting artifacts but preserve content structure
#         # These are common in direct PDF/Word extraction
#         formatting_artifact_patterns = [
#             r'^\s*\d{1,3}\s*$',                 # Standalone page numbers on their own lines
#             r'^\s*[•▪▫‣⁃]\s*$',                # Bullet points on separate lines
#             r'^\s*[A-Z]{1,3}\s*$',             # Very short all-caps artifacts (but preserve real headers)
#         ]
        
#         lines = text.split('\n')
#         cleaned_lines = []
        
#         for line in lines:
#             line_stripped = line.strip()
#             is_artifact = False
            
#             # Check if line matches formatting artifact patterns
#             for pattern in formatting_artifact_patterns:
#                 if re.match(pattern, line):
#                     is_artifact = True
#                     break
            
#             if not is_artifact:
#                 cleaned_lines.append(line)
        
#         return '\n'.join(cleaned_lines)

#     def _fix_obvious_character_errors_only(self, text: str) -> str:
#         """Fix only the most obvious character errors from direct text extraction"""
#         # Very conservative fixes - targeting direct extraction artifacts, not OCR errors
#         # These are encoding/extraction issues that can occur with PyMuPDF, python-docx, pandas
        
#         direct_extraction_fixes = {
#             # Common encoding issues in direct text extraction
#             r'\u00a0': ' ',              # Non-breaking space to regular space
#             r'\u2018': "'",              # Left single quotation mark
#             r'\u2019': "'",              # Right single quotation mark  
#             r'\u201c': '"',              # Left double quotation mark
#             r'\u201d': '"',              # Right double quotation mark
#             r'\u2013': '-',              # En dash to hyphen
#             r'\u2014': '--',             # Em dash to double hyphen
#             r'\u2026': '...',            # Horizontal ellipsis
            
#             # Table extraction artifacts (from Excel/Word tables)
#             r'\|\s*\|': '|',             # Multiple pipes with spaces
#             r'\s+\|\s+': ' | ',          # Normalize pipe spacing in tables
            
#             # Word document extraction issues
#             r'\x0c': '',                 # Form feed characters (page breaks)
#             r'\x0b': '',                 # Vertical tab characters
            
#             # PDF extraction artifacts
#             r'(?<=\w)\u00ad(?=\w)': '',  # Soft hyphens within words
#         }
        
#         for pattern, replacement in direct_extraction_fixes.items():
#             text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
#         # Only fix very obvious word errors that could come from direct extraction
#         # These are much rarer than OCR errors but can still occur
#         super_obvious_word_fixes = {
#             r'\bc0mpared\b': 'compared',     # 0/o confusion (rare in direct extraction)
#             r'\bperf0rmance\b': 'performance', # 0/o confusion
#             r'\bstr0ng\b': 'strong',         # 0/o confusion
#             r'\bm0re\b': 'more',             # 0/o confusion
#             r'\b0ther\b': 'other',           # 0/o confusion
#         }
        
#         for pattern, replacement in super_obvious_word_fixes.items():
#             text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
#         return text

#     def _apply_minimal_spacy_filtering(self, text: str, document_id: str) -> str:
#         """Apply minimal spaCy filtering with maximum semantic preservation"""
#         try:
#             # Process in smaller chunks to preserve context
#             max_chunk_size = 500000  # 500K chars
#             if len(text) <= max_chunk_size:
#                 return self._minimal_spacy_process_chunk(text, document_id)
            
#             # For larger texts, process in semantic chunks (paragraphs)
#             paragraphs = text.split('\n\n')
#             processed_paragraphs = []
#             current_chunk = ""
            
#             for paragraph in paragraphs:
#                 if len(current_chunk) + len(paragraph) > max_chunk_size and current_chunk:
#                     # Process current chunk
#                     processed_chunk = self._minimal_spacy_process_chunk(current_chunk, document_id)
#                     processed_paragraphs.append(processed_chunk)
#                     current_chunk = paragraph
#                 else:
#                     if current_chunk:
#                         current_chunk += '\n\n' + paragraph
#                     else:
#                         current_chunk = paragraph
            
#             # Process final chunk
#             if current_chunk:
#                 processed_chunk = self._minimal_spacy_process_chunk(current_chunk, document_id)
#                 processed_paragraphs.append(processed_chunk)
            
#             return '\n\n'.join(processed_paragraphs)
            
#         except Exception as e:
#             self.logger.warning(f"[{document_id}] spaCy minimal filtering failed: {e}")
#             return text

#     def _minimal_spacy_process_chunk(self, text: str, document_id: str) -> str:
#         """Process a chunk with minimal spaCy filtering - preserve almost everything"""
#         try:
#             doc = self.nlp(text)
#             preserved_sentences = []
            
#             for sent in doc.sents:
#                 sentence_text = sent.text.strip()
                
#                 # Very lenient filtering - only remove obviously meaningless content
#                 if self._is_obviously_junk_sentence(sent, sentence_text):
#                     continue
                
#                 preserved_sentences.append(sentence_text)
            
#             return ' '.join(preserved_sentences)
            
#         except Exception as e:
#             self.logger.debug(f"[{document_id}] Chunk processing failed: {e}")
#             return text

#     def _is_obviously_junk_sentence(self, sent_obj, sentence_text: str) -> bool:
#         """Check if sentence is obviously junk - very high threshold"""
        
#         # Only remove if extremely obvious junk
#         if len(sentence_text) < 3:  # Very short fragments
#             return True
        
#         # Check if sentence is mostly special characters
#         alpha_chars = sum(1 for c in sentence_text if c.isalpha())
#         total_chars = len(sentence_text)
#         alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
        
#         if alpha_ratio < 0.2:  # Less than 20% alphabetic characters
#             return True
        
#         # Check if it's obviously garbled (no real words)
#         tokens = [token for token in sent_obj if token.is_alpha and len(token.text) > 1]
#         if len(tokens) == 0:
#             return True
        
#         # Only remove if absolutely no recognizable word patterns
#         # Be extremely conservative here
#         words = sentence_text.split()
#         has_normal_words = False
#         for word in words:
#             clean_word = word.strip('.,!?";:').lower()
#             # Check if word has normal English patterns
#             if len(clean_word) > 2 and clean_word.isalpha():
#                 # Check for vowel patterns (most English words have vowels)
#                 vowels = sum(1 for c in clean_word if c in 'aeiou')
#                 if vowels > 0:
#                     has_normal_words = True
#                     break
        
#         if has_normal_words:
#             return False
        
#         return True

#     def _basic_semantic_preserving_filter(self, text: str) -> str:
#         """Basic filtering without spaCy that preserves semantic meaning"""
#         # Split into sentences and filter very conservatively
#         sentences = re.split(r'(?<=[.!?])\s+', text)
#         preserved_sentences = []
        
#         for sentence in sentences:
#             sentence = sentence.strip()
            
#             # Only remove obviously meaningless content
#             if len(sentence) < 3:
#                 continue
            
#             # Check alphabetic ratio - be very lenient
#             alpha_chars = sum(1 for c in sentence if c.isalpha())
#             total_chars = len(sentence)
#             alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
            
#             if alpha_ratio < 0.2:  # Less than 20% alphabetic
#                 continue
            
#             # Check if it has any recognizable words
#             words = sentence.split()
#             recognizable_words = [w for w in words if len(w) > 1 and any(c.isalpha() for c in w)]
            
#             if len(recognizable_words) == 0:
#                 continue
            
#             preserved_sentences.append(sentence)
        
#         return '. '.join(preserved_sentences)
