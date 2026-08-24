# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Structured File Extractor
=========================
Extracts records from structured Excel, CSV, and JSON files for micro-embedding.
Enables record-level semantic search via the SaaS embedding pipeline.

Features:
- Auto-detection of tabular data with intelligent header detection
- Header injection into each record for AI context
- Smart header-row finder for title-row Excel files
- No hard record limit — 100MB file size cap is the natural boundary
- Batch processing in groups of 100
"""

import io
import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple, Generator
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration - read from environment variables
MIN_ROWS_FOR_RECORD_EXTRACTION = int(os.getenv("MIN_ROWS_FOR_RECORD_EXTRACTION", 50))  # Only extract records if >50 rows
MAX_RECORDS_PER_FILE = int(os.getenv("MAX_RECORDS_PER_FILE", 10000))  # Upper limit per file
BATCH_SIZE = 100  # Process records in batches

# Try to import pandas
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logger.warning("pandas not available - Excel record extraction disabled")


def detect_structured_csv(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Detect if CSV file contains structured tabular data suitable for record extraction.
    
    Returns:
        Dict with:
        - is_structured: bool - True if file has >50 rows of consistent data
        - total_rows: int - Total row count
        - headers: List[str] - Column names
    """
    if not PANDAS_AVAILABLE:
        return {"is_structured": False, "reason": "pandas not available"}
    
    try:
        csv_stream = io.BytesIO(file_content)
        df = pd.read_csv(csv_stream)
        
        if df.empty:
            return {"is_structured": False, "reason": "CSV file is empty"}
        
        row_count = len(df)
        col_count = len(df.columns)
        headers = [str(col) for col in df.columns]
        
        # Check if this file has tabular data (at least 1 row and 2 columns)
        has_tabular_data = row_count >= 1 and col_count >= 2
        total_rows = row_count if has_tabular_data else 0
        
        is_structured = total_rows > MIN_ROWS_FOR_RECORD_EXTRACTION
        has_tabular_data = total_rows > 0
        
        return {
            "is_structured": is_structured,
            "has_tabular_data": has_tabular_data,
            "total_rows": total_rows,
            "headers": headers,
            "columns": col_count,
            "will_extract_records": has_tabular_data,
            "max_records": total_rows if has_tabular_data else 0
        }
        
    except Exception as e:
        logger.error(f"Error detecting CSV structure: {e}")
        return {"is_structured": False, "error": str(e)}


def extract_csv_records(
    file_content: bytes,
    filename: str,
    max_records: Optional[int] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Extract individual rows from CSV as records for micro-embedding.
    
    Each record includes:
    - file_context: File header for AI context
    - headers: Column names
    - row_number: Original row number
    - data: Dict of column -> value
    
    Yields:
        Dict for each row (max 1000 records)
    """
    if not PANDAS_AVAILABLE:
        logger.error("pandas not available - cannot extract CSV records")
        return
    
    try:
        csv_stream = io.BytesIO(file_content)
        df = pd.read_csv(csv_stream)
        
        if df.empty:  # Skip truly empty files
            return
        
        # Clean data
        df = df.fillna("")
        headers = [str(col) for col in df.columns]
        
        # File context header for injection into each record
        file_context = {
            "filename": filename,
            "sheet_name": "CSV",
            "total_columns": len(headers),
            "headers": headers
        }
        
        records_yielded = 0
        
        # Extract rows
        for idx, row in df.iterrows():
            if max_records and records_yielded >= max_records:
                logger.warning(f"Reached max records limit ({max_records}) - stopping extraction")
                break
            
            row_number = idx + 2  # 1-indexed, +1 for header
            row_data = {}
            
            for col in headers:
                value = row[col]
                # Convert to string, handle various types
                if pd.isna(value) or value == "":
                    row_data[col] = ""
                elif isinstance(value, (int, float)):
                    row_data[col] = value
                else:
                    row_data[col] = str(value)
            
            # Generate unique record ID
            record_id = f"CSV_row_{row_number}"
            
            yield {
                "record_id": record_id,
                "file_context": file_context,
                "row_number": row_number,
                "data": row_data,
                "source_type": "excel_row"  # Use same source_type for consistent SaaS formatting
            }
            
            records_yielded += 1
        
        logger.info(f"Extracted {records_yielded} records from CSV file '{filename}'")
        
    except Exception as e:
        logger.error(f"Error extracting CSV records: {e}")


def _find_header_row(excel_file, sheet_name: str, max_scan_rows: int = 10) -> Optional[int]:
    """
    Detect the actual header row in an Excel sheet.
    
    When the first row is a title/merged-cell (e.g. "CLASS 1-C TIME TABLE (2025-26)"),
    pandas treats it as column headers, producing mostly 'Unnamed:' columns.
    This function scans the first few rows to find the real header row.
    
    Returns:
        The 0-based row index to use as header, or None if the default (row 0) is fine.
    """
    try:
        # Read with no header to get raw rows
        df_raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, nrows=max_scan_rows)
        if df_raw.empty or len(df_raw) < 2:
            return None
        
        # Check if default header (row 0) looks like a real header
        row0_values = [str(v) for v in df_raw.iloc[0] if pd.notna(v) and str(v).strip()]
        total_cols = len(df_raw.columns)
        
        # Heuristic: if row 0 has very few non-empty values relative to total columns,
        # it's likely a title/merged row, not a real header
        if len(row0_values) <= max(1, total_cols // 3):
            # Scan rows 1..max_scan_rows for a better header candidate
            for i in range(1, min(len(df_raw), max_scan_rows)):
                row_values = [str(v) for v in df_raw.iloc[i] if pd.notna(v) and str(v).strip()]
                # A good header row has mostly non-empty, unique string values
                if len(row_values) >= max(2, total_cols // 2):
                    logger.info(f"[HEADER_DETECT] Sheet '{sheet_name}': row 0 looks like title, using row {i} as header")
                    return i
            
            # No better header found — fall back to header=None (auto-generated Column_0, Column_1, ...)
            logger.info(f"[HEADER_DETECT] Sheet '{sheet_name}': no clear header row found, using auto-generated columns")
            return -1  # Sentinel: use header=None
        
        return None  # Default header (row 0) is fine
    except Exception as e:
        logger.debug(f"[HEADER_DETECT] Error scanning for header row: {e}")
        return None


def _read_excel_sheet_smart(excel_file, sheet_name: str) -> 'pd.DataFrame':
    """
    Read an Excel sheet with intelligent header detection.
    Falls back to auto-generated column names if no clear header row is found.
    """
    header_row = _find_header_row(excel_file, sheet_name)
    
    if header_row is None:
        # Default pandas behavior — row 0 is the header
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
    elif header_row == -1:
        # No clear header — use auto-generated column names
        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
        df.columns = [f"Column_{i+1}" for i in range(len(df.columns))]
    else:
        # Use the detected header row
        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row)
    
    # Clean up 'Unnamed: X' columns with meaningful auto-names
    new_cols = []
    for i, col in enumerate(df.columns):
        col_str = str(col)
        if col_str.startswith("Unnamed:"):
            new_cols.append(f"Column_{i+1}")
        else:
            new_cols.append(col_str)
    df.columns = new_cols
    
    return df


def detect_structured_excel(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Detect if Excel file contains structured tabular data suitable for record extraction.
    
    Returns:
        Dict with:
        - is_structured: bool - True if file has >50 rows of consistent data
        - total_rows: int - Total row count across all sheets
        - sheets: List[Dict] - Per-sheet info (name, rows, columns, headers)
    """
    if not PANDAS_AVAILABLE:
        return {"is_structured": False, "reason": "pandas not available"}
    
    try:
        excel_stream = io.BytesIO(file_content)
        excel_file = pd.ExcelFile(excel_stream)
        
        sheets_info = []
        total_rows = 0
        
        for sheet_name in excel_file.sheet_names:
            try:
                df = _read_excel_sheet_smart(excel_file, sheet_name)
                
                if df.empty:
                    continue
                
                row_count = len(df)
                col_count = len(df.columns)
                headers = [str(col) for col in df.columns]
                
                # Check if this sheet has tabular data (at least 1 row and 2 columns)
                is_sheet_structured = row_count >= 1 and col_count >= 2
                
                sheets_info.append({
                    "sheet_name": sheet_name,
                    "rows": row_count,
                    "columns": col_count,
                    "headers": headers,
                    "is_structured": is_sheet_structured
                })
                
                if is_sheet_structured:
                    total_rows += row_count
                    
            except Exception as e:
                logger.warning(f"Error reading sheet '{sheet_name}': {e}")
                continue
        
        is_structured = total_rows > MIN_ROWS_FOR_RECORD_EXTRACTION
        has_tabular_data = total_rows > 0
        
        return {
            "is_structured": is_structured,
            "has_tabular_data": has_tabular_data,
            "total_rows": total_rows,
            "sheets": sheets_info,
            "structured_sheets": [s for s in sheets_info if s.get("is_structured")],
            "will_extract_records": has_tabular_data,
            "max_records": total_rows if has_tabular_data else 0
        }
        
    except Exception as e:
        logger.error(f"Error detecting Excel structure: {e}")
        return {"is_structured": False, "error": str(e)}


def detect_structured_json(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Detect if JSON file contains an array of objects suitable for record extraction.
    
    Returns:
        Dict with:
        - is_structured: bool - True if file has >50 similar objects
        - total_objects: int - Number of objects found
        - array_path: str - Path to the array (e.g., "data.deals" or "root")
        - sample_keys: List[str] - Keys from first object
    """
    try:
        # Decode JSON
        json_str = file_content.decode('utf-8')
        data = json.loads(json_str)
        
        # Check various structures
        result = _find_object_array(data)
        
        if result:
            array_path, objects = result
            total_objects = len(objects)
            
            # Get sample keys from first object
            sample_keys = []
            if objects and isinstance(objects[0], dict):
                sample_keys = list(objects[0].keys())[:20]  # First 20 keys
            
            is_structured = total_objects > MIN_ROWS_FOR_RECORD_EXTRACTION
            has_tabular_data = total_objects > 0
            
            return {
                "is_structured": is_structured,
                "has_tabular_data": has_tabular_data,
                "total_objects": total_objects,
                "array_path": array_path,
                "sample_keys": sample_keys,
                "will_extract_records": has_tabular_data,
                "max_records": total_objects if has_tabular_data else 0
            }
        
        return {
            "is_structured": False,
            "reason": "No array of objects found"
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return {"is_structured": False, "error": f"Invalid JSON: {e}"}
    except Exception as e:
        logger.error(f"Error detecting JSON structure: {e}")
        return {"is_structured": False, "error": str(e)}


def _find_object_array(data: Any, path: str = "root") -> Optional[Tuple[str, List[Dict]]]:
    """
    Recursively find an array of objects in JSON data.
    
    Returns:
        Tuple of (path, array) if found, None otherwise
    """
    # Check if data itself is an array of objects
    if isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            return (path, data)
    
    # Check nested objects for arrays
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path != "root" else key
            
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                return (new_path, value)
            
            # Recurse one level deep for common patterns (data.items, records, etc.)
            if isinstance(value, dict):
                result = _find_object_array(value, new_path)
                if result:
                    return result
    
    return None


def extract_excel_records(
    file_content: bytes,
    filename: str,
    max_records: Optional[int] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Extract individual rows from Excel as records for micro-embedding.
    
    Each record includes:
    - file_context: File and sheet header for AI context
    - headers: Column names
    - row_number: Original row number
    - data: Dict of column -> value
    - formatted_text: Pre-formatted text with header injection
    
    Yields:
        Dict for each row (max 1000 records)
    """
    if not PANDAS_AVAILABLE:
        logger.error("pandas not available - cannot extract Excel records")
        return
    
    try:
        excel_stream = io.BytesIO(file_content)
        excel_file = pd.ExcelFile(excel_stream)
        
        records_yielded = 0
        
        for sheet_name in excel_file.sheet_names:
            if max_records and records_yielded >= max_records:
                logger.warning(f"Reached max records limit ({max_records}) - stopping extraction")
                break
                
            try:
                df = _read_excel_sheet_smart(excel_file, sheet_name)
                
                if df.empty:  # Skip truly empty sheets
                    continue
                
                # Clean data
                df = df.fillna("")
                headers = [str(col) for col in df.columns]
                
                # File context header for injection into each record
                file_context = {
                    "filename": filename,
                    "sheet_name": sheet_name,
                    "total_columns": len(headers),
                    "headers": headers
                }
                
                # Extract rows
                for idx, row in df.iterrows():
                    if max_records and records_yielded >= max_records:
                        break
                    
                    row_number = idx + 2  # Excel rows are 1-indexed, +1 for header
                    row_data = {}
                    
                    for col in headers:
                        value = row[col]
                        # Convert to string, handle various types
                        if pd.isna(value) or value == "":
                            row_data[col] = ""
                        elif isinstance(value, (int, float)):
                            # Keep numbers as-is for formatting
                            row_data[col] = value
                        else:
                            row_data[col] = str(value)
                    
                    # Generate unique record ID
                    record_id = f"{sheet_name}_row_{row_number}"
                    
                    yield {
                        "record_id": record_id,
                        "file_context": file_context,
                        "row_number": row_number,
                        "data": row_data,
                        "source_type": "excel_row"
                    }
                    
                    records_yielded += 1
                    
            except Exception as e:
                logger.warning(f"Error extracting rows from sheet '{sheet_name}': {e}")
                continue
        
        logger.info(f"Extracted {records_yielded} records from Excel file '{filename}'")
        
    except Exception as e:
        logger.error(f"Error extracting Excel records: {e}")


def extract_json_records(
    file_content: bytes,
    filename: str,
    max_records: Optional[int] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Extract individual objects from JSON array for micro-embedding.
    
    Each record includes:
    - file_context: File and array info for AI context
    - object_index: Position in array
    - data: The object data
    - formatted_text: Pre-formatted text with header injection
    
    Yields:
        Dict for each object (max 1000 records)
    """
    try:
        json_str = file_content.decode('utf-8')
        data = json.loads(json_str)
        
        # Find the array of objects
        result = _find_object_array(data)
        
        if not result:
            logger.warning(f"No array of objects found in JSON file '{filename}'")
            return
        
        array_path, objects = result
        
        # Detect object type from path or first object keys
        detected_type = _detect_json_object_type(array_path, objects[0] if objects else {})
        
        # File context header for injection
        file_context = {
            "filename": filename,
            "array_path": array_path,
            "detected_type": detected_type,
            "total_objects": len(objects)
        }
        
        records_yielded = 0
        
        for idx, obj in enumerate(objects):
            if max_records and records_yielded >= max_records:
                logger.warning(f"Reached max records limit ({max_records}) - stopping extraction")
                break
            
            if not isinstance(obj, dict):
                continue
            
            # Try to find a natural ID in the object
            obj_id = (
                obj.get('id') or 
                obj.get('Id') or 
                obj.get('_id') or 
                obj.get('ID') or
                f"idx_{idx}"
            )
            
            record_id = f"{detected_type}_{obj_id}"
            
            yield {
                "record_id": str(record_id),
                "file_context": file_context,
                "object_index": idx,
                "data": obj,
                "source_type": "json_record"
            }
            
            records_yielded += 1
        
        logger.info(f"Extracted {records_yielded} records from JSON file '{filename}'")
        
    except Exception as e:
        logger.error(f"Error extracting JSON records: {e}")


def _detect_json_object_type(array_path: str, sample_obj: Dict[str, Any]) -> str:
    """
    Try to detect the type of objects in the JSON array.
    
    Uses array path and object keys to guess the type.
    """
    # Common CRM/business object patterns
    type_indicators = {
        # From path
        "deals": "deal",
        "contacts": "contact",
        "companies": "company",
        "accounts": "account",
        "opportunities": "opportunity",
        "leads": "lead",
        "customers": "customer",
        "invoices": "invoice",
        "orders": "order",
        "products": "product",
        "tickets": "ticket",
        "users": "user",
        "employees": "employee",
        "transactions": "transaction",
        "payments": "payment",
        "subscriptions": "subscription",
    }
    
    # Check path
    path_lower = array_path.lower()
    for pattern, obj_type in type_indicators.items():
        if pattern in path_lower:
            return obj_type
    
    # Check object keys for hints
    keys_lower = [k.lower() for k in sample_obj.keys()]
    
    if any(k in keys_lower for k in ['dealname', 'deal_name', 'dealstage', 'deal_stage']):
        return "deal"
    if any(k in keys_lower for k in ['email', 'firstname', 'lastname', 'phone']):
        return "contact"
    if any(k in keys_lower for k in ['amount', 'total', 'invoice_number', 'invoice_date']):
        return "invoice"
    if any(k in keys_lower for k in ['ticket_id', 'subject', 'priority', 'status']):
        return "ticket"
    if any(k in keys_lower for k in ['product_name', 'sku', 'price', 'inventory']):
        return "product"
    if any(k in keys_lower for k in ['order_id', 'order_date', 'shipping']):
        return "order"
    
    return "record"  # Generic fallback


def get_records_in_batches(
    records: Generator[Dict[str, Any], None, None],
    batch_size: int = BATCH_SIZE
) -> Generator[List[Dict[str, Any]], None, None]:
    """
    Group records into batches for processing.
    
    Args:
        records: Generator of records
        batch_size: Number of records per batch (default 100)
        
    Yields:
        Lists of records (batches)
    """
    batch = []
    
    for record in records:
        batch.append(record)
        
        if len(batch) >= batch_size:
            yield batch
            batch = []
    
    # Yield remaining records
    if batch:
        yield batch
