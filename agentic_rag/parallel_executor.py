"""
Parallel Execution Manager for Agentic RAG System
================================================

This module provides parallel execution capabilities for optimizing
performance when running multiple retrieval strategies simultaneously.
"""

import asyncio
import logging
from typing import List, Dict, Any, Callable, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

logger = logging.getLogger(__name__)

class ParallelExecutionManager:
    """Manages parallel execution of retrieval operations"""
    
    def __init__(self, max_workers: int = 3, timeout: float = 30.0):
        """
        Initialize parallel execution manager
        
        Args:
            max_workers: Maximum number of concurrent workers
            timeout: Timeout for individual operations in seconds
        """
        self.max_workers = max_workers
        self.timeout = timeout
        logger.info(f"🚀 ParallelExecutionManager initialized with {max_workers} workers, {timeout}s timeout")
    
    async def execute_retrievals_parallel(
        self,
        retrieval_tasks: List[Dict[str, Any]],
        fallback_on_error: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Execute multiple retrieval tasks in parallel
        
        Args:
            retrieval_tasks: List of task dictionaries with:
                - 'name': Task identifier
                - 'agent': Agent instance
                - 'method': Method name to call
                - 'args': Arguments for the method
                - 'kwargs': Keyword arguments for the method
            fallback_on_error: Whether to continue with other tasks if one fails
            
        Returns:
            Dictionary mapping task names to their results
        """
        start_time = time.time()
        results = {}
        errors = {}
        
        logger.info(f"🔄 Starting parallel execution of {len(retrieval_tasks)} tasks")
        
        try:
            # Create semaphore to limit concurrent executions
            semaphore = asyncio.Semaphore(self.max_workers)
            
            # Create tasks for async execution
            async_tasks = []
            for task_config in retrieval_tasks:
                task = self._create_async_task(task_config, semaphore)
                async_tasks.append(task)
            
            # Execute all tasks with timeout
            completed_results = await asyncio.wait_for(
                asyncio.gather(*async_tasks, return_exceptions=True),
                timeout=self.timeout
            )
            
            # Process results
            for i, result in enumerate(completed_results):
                task_name = retrieval_tasks[i]['name']
                
                if isinstance(result, Exception):
                    logger.error(f"❌ Task '{task_name}' failed: {result}")
                    errors[task_name] = str(result)
                    if fallback_on_error:
                        results[task_name] = []  # Empty result for failed task
                    else:
                        raise result
                else:
                    results[task_name] = result
                    logger.info(f"✅ Task '{task_name}' completed successfully")
            
            execution_time = time.time() - start_time
            logger.info(f"✅ Parallel execution completed in {execution_time:.2f}s")
            
            if errors:
                logger.warning(f"⚠️ {len(errors)} tasks had errors: {list(errors.keys())}")
            
            return results
            
        except asyncio.TimeoutError:
            logger.error(f"❌ Parallel execution timed out after {self.timeout}s")
            if fallback_on_error:
                return {task['name']: [] for task in retrieval_tasks}
            raise
            
        except Exception as e:
            logger.error(f"❌ Parallel execution failed: {e}")
            if fallback_on_error:
                return {task['name']: [] for task in retrieval_tasks}
            raise
    
    async def _create_async_task(
        self,
        task_config: Dict[str, Any],
        semaphore: asyncio.Semaphore
    ) -> List[Dict[str, Any]]:
        """Create and execute an async task with semaphore control"""
        async with semaphore:
            try:
                agent = task_config['agent']
                method_name = task_config['method']
                args = task_config.get('args', [])
                kwargs = task_config.get('kwargs', {})
                
                # Get the method from the agent
                method = getattr(agent, method_name)
                
                # Execute the method (assume it's async)
                if asyncio.iscoroutinefunction(method):
                    result = await method(*args, **kwargs)
                else:
                    # Run sync method in thread pool
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: method(*args, **kwargs))
                
                return result if isinstance(result, list) else []
                
            except Exception as e:
                logger.error(f"❌ Task execution failed: {e}")
                raise
    
    async def execute_with_priority(
        self,
        high_priority_tasks: List[Dict[str, Any]],
        low_priority_tasks: List[Dict[str, Any]],
        high_priority_timeout: float = 10.0
    ) -> Tuple[Dict[str, List], Dict[str, List]]:
        """
        Execute tasks with priority - high priority first, then low priority
        
        Args:
            high_priority_tasks: Critical tasks to execute first
            low_priority_tasks: Optional tasks to execute if time permits
            high_priority_timeout: Timeout for high priority tasks
            
        Returns:
            Tuple of (high_priority_results, low_priority_results)
        """
        logger.info(f"🔥 Executing {len(high_priority_tasks)} high priority tasks first")
        
        # Execute high priority tasks first
        high_results = await self.execute_retrievals_parallel(
            high_priority_tasks,
            fallback_on_error=True
        )
        
        # Check remaining time for low priority tasks
        remaining_time = max(0, self.timeout - high_priority_timeout)
        
        if remaining_time > 1.0 and low_priority_tasks:
            logger.info(f"⚡ Executing {len(low_priority_tasks)} low priority tasks with {remaining_time:.1f}s remaining")
            
            # Temporarily reduce timeout for low priority
            original_timeout = self.timeout
            self.timeout = remaining_time
            
            try:
                low_results = await self.execute_retrievals_parallel(
                    low_priority_tasks,
                    fallback_on_error=True
                )
            finally:
                self.timeout = original_timeout
        else:
            logger.info("⏰ No time remaining for low priority tasks")
            low_results = {task['name']: [] for task in low_priority_tasks}
        
        return high_results, low_results
    
    async def execute_with_fallback_chain(
        self,
        primary_tasks: List[Dict[str, Any]],
        fallback_tasks: List[Dict[str, Any]],
        min_required_results: int = 1
    ) -> Dict[str, List]:
        """
        Execute tasks with fallback chain - if primary fails, try fallback
        
        Args:
            primary_tasks: Primary retrieval tasks to try first
            fallback_tasks: Fallback tasks to try if primary doesn't yield enough results
            min_required_results: Minimum number of successful tasks needed
            
        Returns:
            Combined results from primary and fallback tasks
        """
        logger.info(f"🎯 Executing primary tasks with fallback chain")
        
        # Execute primary tasks
        primary_results = await self.execute_retrievals_parallel(
            primary_tasks,
            fallback_on_error=True
        )
        
        # Count successful primary results
        successful_primary = sum(
            1 for results in primary_results.values() 
            if results and len(results) > 0
        )
        
        logger.info(f"📊 Primary execution: {successful_primary}/{len(primary_tasks)} tasks successful")
        
        # Execute fallback if needed
        if successful_primary < min_required_results and fallback_tasks:
            logger.info(f"🔄 Executing fallback tasks (need {min_required_results - successful_primary} more)")
            
            fallback_results = await self.execute_retrievals_parallel(
                fallback_tasks,
                fallback_on_error=True
            )
            
            # Merge results (primary takes precedence)
            combined_results = {**fallback_results, **primary_results}
            return combined_results
        
        return primary_results
    
    def create_retrieval_task(
        self,
        name: str,
        agent: Any,
        method: str = "retrieve",
        *args,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Helper method to create a retrieval task configuration
        
        Args:
            name: Task identifier
            agent: Agent instance
            method: Method name to call on the agent
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
            
        Returns:
            Task configuration dictionary
        """
        return {
            'name': name,
            'agent': agent,
            'method': method,
            'args': args,
            'kwargs': kwargs
        }

class OptimizedRetrievalExecutor:
    """Optimized executor that uses parallel execution for better performance"""
    
    def __init__(self, agents: Dict[str, Any], max_workers: int = 3):
        """
        Initialize optimized executor
        
        Args:
            agents: Dictionary of agent instances
            max_workers: Maximum parallel workers
        """
        self.agents = agents
        self.parallel_manager = ParallelExecutionManager(max_workers=max_workers)
        logger.info(f"🚀 OptimizedRetrievalExecutor initialized with {len(agents)} agents")
    
    async def execute_strategy_parallel(
        self,
        strategy_name: str,
        query: str,
        user_id: str,
        **strategy_params
    ) -> Dict[str, List]:
        """
        Execute a specific strategy with optimized parallel execution
        
        Args:
            strategy_name: Name of the strategy to execute
            query: User query
            user_id: User ID
            **strategy_params: Additional parameters for the strategy
            
        Returns:
            Dictionary with results from parallel execution
        """
        tasks = []
        
        if strategy_name == "combined_sources":
            # Personal + Enterprise in parallel
            if self.agents.get('personal'):
                tasks.append(
                    self.parallel_manager.create_retrieval_task(
                        "personal",
                        self.agents['personal'],
                        query=query,
                        user_id=user_id,
                        max_results=strategy_params.get('max_personal', 5)
                    )
                )
            
            if self.agents.get('enterprise') and strategy_params.get('enterprise_token'):
                tasks.append(
                    self.parallel_manager.create_retrieval_task(
                        "enterprise",
                        self.agents['enterprise'],
                        query=query,
                        user_id=user_id,
                        token=strategy_params.get('enterprise_token'),
                        entity_id=strategy_params.get('entity_id'),
                        max_results=strategy_params.get('max_enterprise', 5)
                    )
                )
        
        elif strategy_name == "enterprise_hybrid":
            # General + Entity enterprise searches in parallel
            if self.agents.get('enterprise') and strategy_params.get('enterprise_token'):
                # General enterprise search
                tasks.append(
                    self.parallel_manager.create_retrieval_task(
                        "enterprise_general",
                        self.agents['enterprise'],
                        query=query,
                        user_id=user_id,
                        token=strategy_params.get('enterprise_token'),
                        max_results=strategy_params.get('max_general', 5)
                    )
                )
                
                # Entity-specific search if entity_id provided
                if strategy_params.get('entity_id'):
                    tasks.append(
                        self.parallel_manager.create_retrieval_task(
                            "enterprise_entity",
                            self.agents['enterprise'],
                            query=query,
                            user_id=user_id,
                            token=strategy_params.get('enterprise_token'),
                            entity_id=strategy_params.get('entity_id'),
                            max_results=strategy_params.get('max_entity', 5)
                        )
                    )
        
        if not tasks:
            logger.warning(f"⚠️ No tasks created for strategy '{strategy_name}'")
            return {}
        
        # Execute tasks in parallel
        results = await self.parallel_manager.execute_retrievals_parallel(tasks)
        
        logger.info(f"✅ Strategy '{strategy_name}' executed with {len(results)} parallel tasks")
        return results
    
    async def execute_multi_strategy_parallel(
        self,
        strategies: List[str],
        query: str,
        user_id: str,
        **common_params
    ) -> Dict[str, Dict[str, List]]:
        """
        Execute multiple strategies in parallel
        
        Args:
            strategies: List of strategy names
            query: User query
            user_id: User ID
            **common_params: Common parameters for all strategies
            
        Returns:
            Nested dictionary with results by strategy and source
        """
        strategy_tasks = []
        
        for strategy in strategies:
            # Create a task for each strategy
            task_config = {
                'name': strategy,
                'agent': self,  # Use self as the "agent"
                'method': 'execute_strategy_parallel',
                'kwargs': {
                    'strategy_name': strategy,
                    'query': query,
                    'user_id': user_id,
                    **common_params
                }
            }
            strategy_tasks.append(task_config)
        
        # Execute all strategies in parallel
        results = await self.parallel_manager.execute_retrievals_parallel(strategy_tasks)
        
        logger.info(f"✅ Multi-strategy execution complete: {list(results.keys())}")
        return results
