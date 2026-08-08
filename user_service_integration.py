# # ============================  User Service Integration  =============================
# # Purpose: Integration with MongoDB-based user service for subscription management
# # Features: Pro user validation, subscription status checking
# # ----------------------------------------------------------------------------------------

# import logging
# import asyncio
# import subprocess
# import json
# import os
# import httpx
# from typing import Optional, Dict, Any
# from enum import Enum

# # Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # User service configuration
# USER_SERVICE_BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "https://user-service-memory-assist.azurewebsites.net/api")

# class PlanType(str, Enum):
#     """User subscription plan types"""
#     FREE = "free"
#     STANDARD = "standard" 
#     PRO = "pro"

# class UserSubscription:
#     """User subscription details from user service"""
#     def __init__(self, data: Dict[str, Any]):
#         self.plan_type = data.get("planType", "free")
#         self.status = data.get("status", "active")
#         self.features = data.get("features", {})
#         self.is_valid = data.get("isValidSubscription", False)
#         self.expiry_date = data.get("expiryDate")
#         self.user_id = data.get("user_id")
        
#     @property
#     def is_pro(self) -> bool:
#         return self.plan_type == "pro" and self.is_valid

# async def get_user_subscription_async(user_id: str) -> Optional[UserSubscription]:
#     """
#     Get user subscription from user service (async)
#     """
#     try:
#         timeout = httpx.Timeout(5.0)
#         async with httpx.AsyncClient(timeout=timeout) as client:
#             response = await client.post(
#                 f"{USER_SERVICE_BASE_URL}/get-active-subscription-citra-ai",
#                 json={
#                     "user_id": user_id,
#                     "email": user_id if "@" in user_id else None
#                 },
#                 headers={"Content-Type": "application/json"}
#             )
            
#             if response.status_code == 200:
#                 data = response.json()
#                 return UserSubscription(data.get("subscription", {}))
#             elif response.status_code == 404:
#                 # User not found, return free plan
#                 return UserSubscription({
#                     "planType": "free",
#                     "status": "active",
#                     "features": {
#                         "maxDocuments": 10,
#                         "maxStorageGB": 1,
#                         "aiChatEnabled": True,
#                         "conceptMapEnabled": False,
#                         "advancedSearchEnabled": False
#                     },
#                     "isValidSubscription": True
#                 })
#             else:
#                 logger.error(f"Failed to get subscription: {response.status_code}")
#                 return None
                
#     except Exception as e:
#         logger.error(f"Error getting user subscription: {e}")
#         # Return free plan as fallback
#         return UserSubscription({
#             "planType": "free",
#             "status": "active",
#             "features": {
#                 "maxDocuments": 10,
#                 "maxStorageGB": 1,
#                 "aiChatEnabled": True,
#                 "conceptMapEnabled": False,
#                 "advancedSearchEnabled": False
#             },
#             "isValidSubscription": True
#         })

# def get_user_subscription(user_id: str) -> Optional[UserSubscription]:
#     """
#     Synchronous wrapper for getting user subscription
#     """
#     try:
#         loop = asyncio.get_event_loop()
#         if loop.is_running():
#             # If we're in an async context, return a default free plan
#             # In production, you might want to handle this differently
#             return UserSubscription({
#                 "planType": "free",
#                 "status": "active",
#                 "features": {
#                     "maxDocuments": 10,
#                     "maxStorageGB": 1,
#                     "aiChatEnabled": True,
#                     "conceptMapEnabled": False,
#                     "advancedSearchEnabled": False
#                 },
#                 "isValidSubscription": True
#             })
#         else:
#             return asyncio.run(get_user_subscription_async(user_id))
#     except Exception as e:
#         logger.error(f"Error in sync wrapper: {e}")
#         return UserSubscription({
#             "planType": "free",
#             "status": "active",
#             "features": {
#                 "maxDocuments": 10,
#                 "maxStorageGB": 1,
#                 "aiChatEnabled": True,
#                 "conceptMapEnabled": False,
#                 "advancedSearchEnabled": False
#             },
#             "isValidSubscription": True
#         })

# async def validate_feature_access(user_id: str, feature: str) -> bool:
#     """
#     Validate if user has access to a specific feature
#     """
#     try:
#         subscription = await get_user_subscription_async(user_id)
#         if not subscription or not subscription.is_valid:
#             return False
        
#         return subscription.features.get(feature, False)
#     except Exception as e:
#         logger.error(f"Error validating feature access: {e}")
#         return False

# # Backward compatibility with existing code
# class PlanFeatures:
#     """Compatibility class for existing code"""
#     def __init__(self, subscription: UserSubscription):
#         self.max_documents = subscription.features.get("maxDocuments", 10)
#         self.max_storage_gb = subscription.features.get("maxStorageGB", 1)
#         self.ai_chat_enabled = subscription.features.get("aiChatEnabled", True)
#         self.concept_map_enabled = subscription.features.get("conceptMapEnabled", False)
#         self.advanced_search_enabled = subscription.features.get("advancedSearchEnabled", False)

# class UserPlan:
#     """Compatibility class for existing code"""
#     def __init__(self, subscription: UserSubscription):
#         self.user_id = subscription.user_id
#         self.plan_type = subscription.plan_type
#         self.features = PlanFeatures(subscription)

# def get_user_plan(user_id: str) -> Optional[UserPlan]:
#     """
#     Get user plan (for backward compatibility)
#     """
#     try:
#         subscription = get_user_subscription(user_id)
#         return UserPlan(subscription) if subscription else None
#     except Exception as e:
#         logger.error(f"Error getting user plan: {e}")
#         return None
