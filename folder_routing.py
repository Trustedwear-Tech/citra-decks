"""
Folder routing logic for different upload sources and content types
"""

def determine_upload_folder(
    content_type: str,
    upload_source: str = None,
    selected_folder: str = None,
    file_type: str = None
) -> str:
    """
    Determine the appropriate folder for uploaded content based on type and source.
    
    Args:
        content_type: Type of content ('document', 'audio', 'video', 'note', 'recording')
        upload_source: Source of upload ('preload', 'upload_documents', 'upload_images', 'upload_audio', 'google_drive', 'recording', 'meeting_recording', 'note_creation', 'upload_video')
        selected_folder: User-selected folder (if any)
        file_type: File extension/type for additional context
        
    Returns:
        str: The folder ID where content should be stored
        
    Folder routing rules (updated for unified "general" folder):
    1. If folder is selected -> Use selected folder (respects user choice)
    2. If no folder selected -> Use 'general' as default for all types
    
    This ensures:
    - Personal uploads: {user_id}/personal/{folder_id or 'general'}/{content_type}
    - Enterprise uploads: {user_id}/enterprise/{entity_id or 'general'}/{content_type}
    """
    
    # Priority 1: If user selected a specific folder, use it
    if selected_folder and selected_folder.strip():
        # Validate folder ID (basic validation)
        folder = selected_folder.strip()
        if len(folder) > 0:
            return folder
    
    # Priority 2: Default to 'general' for all content types when no folder is selected
    return 'general'


def get_folder_from_upload_context(
    form_data: dict = None,
    query_params: dict = None,
    content_type: str = None,
    upload_source: str = None
) -> str:
    """
    Extract folder information from upload request context.
    
    Args:
        form_data: Form data from multipart uploads
        query_params: Query parameters from request
        content_type: Detected content type
        upload_source: Detected upload source
        
    Returns:
        str: The determined folder ID (human-readable, not UUID)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Try to get folder from various sources
    selected_folder = None
    
    # Debug: Log all form data and query params
    logger.info(f"🔍 FOLDER DEBUG - form_data: {form_data}")
    logger.info(f"🔍 FOLDER DEBUG - query_params: {query_params}")
    
    if form_data:
        # Only use folder_id
        folder_id = form_data.get('folder_id')
        logger.info(f"🔍 FOLDER DEBUG - from form_data: folder_id='{folder_id}'")
        selected_folder = folder_id
    
    if not selected_folder and query_params:
        # Only use folder_id
        folder_id = query_params.get('folder_id')
        logger.info(f"🔍 FOLDER DEBUG - from query_params: folder_id='{folder_id}'")
        selected_folder = folder_id
    
    logger.info(f"🔍 FOLDER DEBUG - selected_folder after extraction: '{selected_folder}'")
    
    # Determine upload source if not provided
    if not upload_source:
        if query_params and query_params.get('source'):
            upload_source = query_params.get('source')
        elif form_data and form_data.get('source'):
            upload_source = form_data.get('source')
        else:
            upload_source = 'upload_documents'  # Default assumption
    
    determined_folder = determine_upload_folder(
        content_type=content_type or 'document',
        upload_source=upload_source,
        selected_folder=selected_folder
    )
    
    logger.info(f"🔍 FOLDER DEBUG - final determined folder: '{determined_folder}'")
    return determined_folder
