import asyncio
import httpx
import ssl
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_ssl_context():
    """Create an SSL context that allows legacy renegotiation."""
    ctx = ssl.create_default_context()
    # Allow legacy renegotiation for older servers (e.g., government sites)
    # OP_LEGACY_SERVER_CONNECT is 0x4 in OpenSSL 3.0+
    try:
        ctx.options |= 0x4
        logger.info("✅ Set OP_LEGACY_SERVER_CONNECT")
    except Exception as e:
        logger.warning(f"⚠️ Could not set OP_LEGACY_SERVER_CONNECT: {e}")
    return ctx

async def test_proxy_ssl():
    url = "https://dceapp.rajasthan.gov.in/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    logger.info(f"🚀 Testing SSL connection to: {url}")
    
    # Test WITHOUT legacy support first (to confirm it fails, though it depends on the local OpenSSL)
    logger.info("--- Testing with default context ---")
    try:
        async with httpx.AsyncClient(verify=True, timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            logger.info(f"✅ Default result: {resp.status_code}")
    except Exception as e:
        logger.error(f"❌ Default failed: {e}")

    # Test WITH legacy support
    logger.info("--- Testing with legacy support context ---")
    try:
        ctx = get_ssl_context()
        async with httpx.AsyncClient(verify=ctx, timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            logger.info(f"✅ Legacy support result: {resp.status_code}")
            logger.info(f"Content length: {len(resp.content)}")
            if resp.status_code == 200:
                logger.info("🎯 SSL Legacy Renegotiation fix confirmed!")
    except Exception as e:
        logger.error(f"❌ Legacy support failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_proxy_ssl())
