"""
Credit Integration Wrapper for Query.py
Provides decorators and helpers to integrate credit checking with existing query functions
"""

import os
import logging
import functools
from typing import Callable, Any, Dict, Optional, Tuple
from middleware import InsufficientCreditsError
# Note: credit_checker function is now in credit_check_client.py

logger = logging.getLogger(__name__)

# Token consumption estimates (approximate tokens per operation)
TOKEN_ESTIMATES = {
    'simple_query': 1000,   # ~500 input + ~500 output tokens
    'complex_query': 4000,  # 2000+ tokens for complex queries
    'audio_transcription': 2000,  # ~tokens per audio transcription
    'file_upload_per_mb': 5000  # ~tokens per MB embedded
}


def extract_token_usage_from_response(response: Any, model_name: str = None) -> Optional[Tuple[int, int]]:
    """
    Extract token usage from LLM API response
    
    Args:
        response: LLM API response object
        model_name: Model name for logging
    
    Returns:
        Tuple[input_tokens, output_tokens] or None if not available
    """
    try:
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            input_tokens = getattr(usage, 'prompt_token_count', 0)
            output_tokens = getattr(usage, 'candidates_token_count', 0)
            
            logger.info(f"💰 Token usage extracted: {input_tokens} input + {output_tokens} output tokens")
            return (input_tokens, output_tokens)
    except Exception as e:
        logger.warning(f"Failed to extract token usage: {e}")
    
    return None


def estimate_query_tokens(query_text: str, has_attachments: bool = False) -> int:
    """
    Estimate token consumption based on query complexity

    Args:
        query_text: The query text
        has_attachments: Whether query has multimodal attachments

    Returns:
        Estimated token count
    """
    query_length = len(query_text)

    # More sophisticated estimation
    if query_length < 100 and not has_attachments:
        return TOKEN_ESTIMATES['simple_query']
    elif has_attachments or query_length > 1000:
        return TOKEN_ESTIMATES['complex_query']
    else:
        # Scale linearly between simple and complex
        ratio = query_length / 1000
        return int(TOKEN_ESTIMATES['simple_query'] + (TOKEN_ESTIMATES['complex_query'] - TOKEN_ESTIMATES['simple_query']) * ratio)


async def check_and_track_query_credits(
    user_id: str,
    email: str,
    query_text: str,
    model_name: str,
    response: Any,
    query_id: Optional[str] = None,
    estimated_cost: Optional[float] = None
) -> Dict[str, Any]:
    """
    Track query credits after LLM call
    
    Args:
        user_id: User's ID
        email: User's email
        query_text: The query text
        model_name: Model used
        response: LLM API response object
        query_id: Optional query identifier
        estimated_cost: Optional pre-estimated cost (for pre-check validation)
    
    Returns:
        Dict with tracking result
    """
    try:
        # Extract token usage from response
        token_usage = extract_token_usage_from_response(response, model_name)
        
        if token_usage:
            input_tokens, output_tokens = token_usage
            
            # Track usage with backend
            result = credit_checker.track_query_usage(
                user_id=user_id,
                email=email,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                query_id=query_id
            )
            
            logger.info(f"💠 Tokens tracked: {result.get('tokens_used', input_tokens + output_tokens)} tokens ({input_tokens} in + {output_tokens} out)")

            return {
                'success': True,
                'tokens_used': {'input': input_tokens, 'output': output_tokens, 'total': result.get('tokens_used', input_tokens + output_tokens)}
            }
        else:
            logger.warning("Token usage not available in response, skipping credit tracking")
            return {
                'success': False,
                'error': 'Token usage not available'
            }
            
    except InsufficientCreditsError as e:
        logger.error(f"❌ Insufficient credits during tracking: {e}")
        return {
            'success': False,
            'error': 'insufficient_credits',
            'message': str(e)
        }
    except Exception as e:
        logger.error(f"❌ Error tracking query credits: {e}")
        return {
            'success': False,
            'error': str(e)
        }


async def pre_check_query_credits(user_id: str, query_text: str, has_attachments: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """
    License model: always passes — no requests are blocked by credit pre-checks.
    """
    return True, {'success': True, 'sufficient': True, 'balance': 999999999, 'message': 'Unlimited (license model)'}


def credit_tracked_query(func: Callable) -> Callable:
    """
    Decorator to add credit tracking to query functions
    
    Usage:
        @credit_tracked_query
        async def process_query(user_id, email, query_text, ...):
            # Your query logic
            return response
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract user_id, email, query_text from args/kwargs
        user_id = kwargs.get('user_id') or (args[0] if len(args) > 0 else None)
        email = kwargs.get('email') or (args[1] if len(args) > 1 else None)
        query_text = kwargs.get('query_text') or kwargs.get('query') or (args[2] if len(args) > 2 else '')
        
        if not user_id or not email:
            logger.warning("Credit tracking skipped: user_id or email not available")
            return await func(*args, **kwargs)
        
        # License model: credit pre-checks are disabled
        # Execute the original function
        response = await func(*args, **kwargs)
        
        # Track credits after execution
        # Note: This requires the response to have token usage metadata
        # For orchestrator responses, token tracking happens inside the orchestrator
        
        return response
    
    return wrapper


# Helper function to add to orchestrator result processing
def add_credit_info_to_response(response_dict: Dict[str, Any], credit_tracking_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add credit tracking information to response dictionary
    
    Args:
        response_dict: The response dictionary
        credit_tracking_result: Result from check_and_track_query_credits
    
    Returns:
        Enhanced response dictionary
    """
    if credit_tracking_result.get('success'):
        response_dict['usage'] = {
            'tokens_used': credit_tracking_result.get('tokens_used'),
        }

    return response_dict
