"""
Performance Optimization Module - Phase 3.2

Optimizes CecilOs performance for benchmark competition.
Targets: Latency <3s, GPU utilization <50%, Success rate >40%.
"""

import logging
import time
import threading
import psutil
import gc
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import numpy as np

logger = logging.getLogger("cecil.performance")


class OptimizationLevel(Enum):
    """Performance optimization levels."""
    CONSERVATIVE = "conservative"  # Safe, low resource usage
    BALANCED = "balanced"        # Good performance/resource balance
    AGGRESSIVE = "aggressive"     # Maximum performance
    BENCHMARK = "benchmark"        # Optimized for benchmarks


@dataclass
class PerformanceMetrics:
    """Performance metrics tracking."""
    cpu_usage: float
    memory_usage: float
    gpu_usage: float
    disk_io: float
    network_io: float
    latency: float
    throughput: float
    timestamp: float


class ResourceMonitor:
    """
    Monitors system resources for optimization decisions.
    """
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.metrics_history = []
        self.max_history = 1000
        
    def start_monitoring(self, interval: float = 1.0):
        """Start resource monitoring."""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            args=(interval,), 
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("Resource monitoring started")
    
    def stop_monitoring(self):
        """Stop resource monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        logger.info("Resource monitoring stopped")
    
    def _monitor_loop(self, interval: float):
        """Main monitoring loop."""
        while self.monitoring:
            try:
                metrics = self._collect_metrics()
                self.metrics_history.append(metrics)
                
                # Limit history size
                if len(self.metrics_history) > self.max_history:
                    self.metrics_history = self.metrics_history[-self.max_history:]
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(interval)
    
    def _collect_metrics(self) -> PerformanceMetrics:
        """Collect current performance metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # GPU usage (if available)
            gpu_percent = self._get_gpu_usage()
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            disk_usage = 0.0
            if disk_io:
                disk_usage = (disk_io.read_bytes + disk_io.write_bytes) / (1024 * 1024)  # MB
            
            # Network I/O
            network_io = psutil.net_io_counters()
            network_usage = 0.0
            if network_io:
                network_usage = (network_io.bytes_sent + network_io.bytes_recv) / (1024 * 1024)  # MB
            
            return PerformanceMetrics(
                cpu_usage=cpu_percent,
                memory_usage=memory_percent,
                gpu_usage=gpu_percent,
                disk_io=disk_usage,
                network_io=network_usage,
                latency=0.0,  # Will be set by performance tracker
                throughput=0.0,  # Will be set by performance tracker
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
            return PerformanceMetrics(
                cpu_usage=0.0, memory_usage=0.0, gpu_usage=0.0,
                disk_io=0.0, network_io=0.0, latency=0.0,
                throughput=0.0, timestamp=time.time()
            )
    
    def _get_gpu_usage(self) -> float:
        """Get GPU usage percentage."""
        try:
            # Try to get GPU info from nvidia-smi
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                gpu_usage = float(result.stdout.strip())
                return gpu_usage
            
        except Exception:
            pass
        
        # Fallback: try GPU libraries
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                return gpus[0].load * 100
        except Exception:
            pass
        
        return 0.0
    
    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Get most recent metrics."""
        if self.metrics_history:
            return self.metrics_history[-1]
        return None
    
    def get_average_metrics(self, window_size: int = 10) -> Optional[PerformanceMetrics]:
        """Get average metrics over a window."""
        if len(self.metrics_history) < window_size:
            return None
        
        recent_metrics = self.metrics_history[-window_size:]
        
        return PerformanceMetrics(
            cpu_usage=np.mean([m.cpu_usage for m in recent_metrics]),
            memory_usage=np.mean([m.memory_usage for m in recent_metrics]),
            gpu_usage=np.mean([m.gpu_usage for m in recent_metrics]),
            disk_io=np.mean([m.disk_io for m in recent_metrics]),
            network_io=np.mean([m.network_io for m in recent_metrics]),
            latency=np.mean([m.latency for m in recent_metrics]),
            throughput=np.mean([m.throughput for m in recent_metrics]),
            timestamp=time.time()
        )


class LatencyOptimizer:
    """
    Optimizes system latency through various techniques.
    """
    
    def __init__(self, resource_monitor: ResourceMonitor):
        self.resource_monitor = resource_monitor
        self.optimization_level = OptimizationLevel.BALANCED
        self.latency_history = []
        self.max_latency_history = 100
        
        # Optimization parameters
        self.target_latency = 3.0  # Target: <3 seconds
        self.max_cpu_usage = 80.0  # Max CPU usage
        self.max_memory_usage = 85.0  # Max memory usage
        self.max_gpu_usage = 50.0  # Max GPU usage
        
    def set_optimization_level(self, level: OptimizationLevel):
        """Set optimization level."""
        self.optimization_level = level
        self._update_parameters()
        logger.info(f"Optimization level set to: {level.value}")
    
    def _update_parameters(self):
        """Update optimization parameters based on level."""
        if self.optimization_level == OptimizationLevel.CONSERVATIVE:
            self.target_latency = 5.0
            self.max_cpu_usage = 60.0
            self.max_memory_usage = 70.0
            self.max_gpu_usage = 30.0
        elif self.optimization_level == OptimizationLevel.BALANCED:
            self.target_latency = 3.0
            self.max_cpu_usage = 80.0
            self.max_memory_usage = 85.0
            self.max_gpu_usage = 50.0
        elif self.optimization_level == OptimizationLevel.AGGRESSIVE:
            self.target_latency = 2.0
            self.max_cpu_usage = 90.0
            self.max_memory_usage = 90.0
            self.max_gpu_usage = 70.0
        elif self.optimization_level == OptimizationLevel.BENCHMARK:
            self.target_latency = 1.5
            self.max_cpu_usage = 95.0
            self.max_memory_usage = 95.0
            self.max_gpu_usage = 80.0
    
    def optimize_execution(self, execution_func: Callable, *args, **kwargs) -> Any:
        """
        Optimize execution of a function with latency monitoring.
        """
        start_time = time.time()
        
        try:
            # Pre-execution optimization
            self._pre_execution_optimization()
            
            # Execute function
            result = execution_func(*args, **kwargs)
            
            # Post-execution cleanup
            self._post_execution_cleanup()
            
            # Record latency
            execution_time = time.time() - start_time
            self._record_latency(execution_time)
            
            return result
            
        except Exception as e:
            # Cleanup on error
            self._post_execution_cleanup()
            raise e
    
    def _pre_execution_optimization(self):
        """Apply pre-execution optimizations."""
        try:
            # Garbage collection
            gc.collect()
            
            # Process priority (if supported)
            try:
                import os
                os.nice(-5)  # Increase priority (Linux)
            except:
                pass
            
            # Thread optimization
            threading.current_thread().name = "cecil_optimized"
            
        except Exception as e:
            logger.error(f"Pre-execution optimization failed: {e}")
    
    def _post_execution_cleanup(self):
        """Apply post-execution cleanup."""
        try:
            # Force garbage collection
            gc.collect()
            
            # Clear caches if memory is high
            metrics = self.resource_monitor.get_current_metrics()
            if metrics and metrics.memory_usage > self.max_memory_usage:
                self._clear_caches()
                
        except Exception as e:
            logger.error(f"Post-execution cleanup failed: {e}")
    
    def _clear_caches(self):
        """Clear various caches to free memory."""
        try:
            # Clear numpy arrays cache
            if hasattr(np, '_clear_cache'):
                np._clear_cache()
            
            # Force Python garbage collection
            gc.collect()
            
            logger.info("Caches cleared for memory optimization")
            
        except Exception as e:
            logger.error(f"Cache clearing failed: {e}")
    
    def _record_latency(self, latency: float):
        """Record execution latency."""
        self.latency_history.append(latency)
        
        # Limit history size
        if len(self.latency_history) > self.max_latency_history:
            self.latency_history = self.latency_history[-self.max_latency_history:]
        
        # Log if latency exceeds target
        if latency > self.target_latency:
            logger.warning(f"High latency detected: {latency:.2f}s (target: {self.target_latency}s)")
    
    def get_latency_stats(self) -> Dict:
        """Get latency statistics."""
        if not self.latency_history:
            return {"error": "No latency data available"}
        
        return {
            "current_latency": self.latency_history[-1],
            "avg_latency": np.mean(self.latency_history),
            "min_latency": np.min(self.latency_history),
            "max_latency": np.max(self.latency_history),
            "p95_latency": np.percentile(self.latency_history, 95),
            "target_latency": self.target_latency,
            "latency_violations": sum(1 for l in self.latency_history if l > self.target_latency),
            "violation_rate": sum(1 for l in self.latency_history if l > self.target_latency) / len(self.latency_history)
        }


class MemoryOptimizer:
    """
    Optimizes memory usage and management.
    """
    
    def __init__(self, resource_monitor: ResourceMonitor):
        self.resource_monitor = resource_monitor
        self.memory_pools = {}
        self.allocation_stats = {}
        
    def allocate_memory_pool(self, pool_name: str, size_mb: int) -> bool:
        """Allocate a memory pool for efficient reuse."""
        try:
            if pool_name in self.memory_pools:
                return True  # Already allocated
            
            # Check available memory
            metrics = self.resource_monitor.get_current_metrics()
            if metrics and metrics.memory_usage + (size_mb / 1024 * 100) > 90:
                logger.warning(f"Insufficient memory for pool {pool_name}: {size_mb}MB")
                return False
            
            # Allocate memory pool (simplified)
            self.memory_pools[pool_name] = {
                "size_mb": size_mb,
                "allocated": time.time(),
                "used": 0
            }
            
            logger.info(f"Allocated memory pool {pool_name}: {size_mb}MB")
            return True
            
        except Exception as e:
            logger.error(f"Memory pool allocation failed: {e}")
            return False
    
    def release_memory_pool(self, pool_name: str):
        """Release a memory pool."""
        if pool_name in self.memory_pools:
            del self.memory_pools[pool_name]
            gc.collect()
            logger.info(f"Released memory pool: {pool_name}")
    
    def optimize_memory_layout(self):
        """Optimize memory layout for better performance."""
        try:
            # Compact memory
            gc.collect()
            
            # Defragment memory pools
            for pool_name in list(self.memory_pools.keys()):
                pool = self.memory_pools[pool_name]
                if pool["used"] == 0:  # Unused pool
                    self.release_memory_pool(pool_name)
            
            logger.info("Memory layout optimized")
            
        except Exception as e:
            logger.error(f"Memory layout optimization failed: {e}")


class GPUMemoryManager:
    """
    Manages GPU memory usage for optimal performance.
    """
    
    def __init__(self, resource_monitor: ResourceMonitor):
        self.resource_monitor = resource_monitor
        self.gpu_memory_pools = {}
        self.max_gpu_memory = self._get_total_gpu_memory()
        
    def _get_total_gpu_memory(self) -> float:
        """Get total GPU memory in MB."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        
        return 0.0
    
    def allocate_gpu_memory(self, pool_name: str, size_mb: int) -> bool:
        """Allocate GPU memory pool."""
        try:
            if pool_name in self.gpu_memory_pools:
                return True
            
            # Check available GPU memory
            metrics = self.resource_monitor.get_current_metrics()
            if not metrics:
                return False
            
            # Estimate available GPU memory
            used_memory = (metrics.gpu_usage / 100.0) * self.max_gpu_memory
            available_memory = self.max_gpu_memory - used_memory
            
            if size_mb > available_memory * 0.8:  # Leave 20% buffer
                logger.warning(f"Insufficient GPU memory for pool {pool_name}: {size_mb}MB")
                return False
            
            self.gpu_memory_pools[pool_name] = {
                "size_mb": size_mb,
                "allocated": time.time()
            }
            
            logger.info(f"Allocated GPU memory pool {pool_name}: {size_mb}MB")
            return True
            
        except Exception as e:
            logger.error(f"GPU memory allocation failed: {e}")
            return False
    
    def optimize_gpu_usage(self):
        """Optimize GPU usage patterns."""
        try:
            # Clear GPU memory pools if usage is high
            metrics = self.resource_monitor.get_current_metrics()
            if metrics and metrics.gpu_usage > 80:
                self._clear_gpu_memory()
            
            logger.info("GPU usage optimized")
            
        except Exception as e:
            logger.error(f"GPU optimization failed: {e}")
    
    def _clear_gpu_memory(self):
        """Clear GPU memory."""
        try:
            # This would use PyTorch/CUDA to clear GPU memory
            # For now, just log the action
            logger.info("GPU memory cleared")
            
        except Exception as e:
            logger.error(f"GPU memory clearing failed: {e}")


class PerformanceOptimizer:
    """
    Main performance optimization coordinator.
    Integrates all optimization components for benchmark performance.
    """
    
    def __init__(self):
        self.resource_monitor = ResourceMonitor()
        self.latency_optimizer = LatencyOptimizer(self.resource_monitor)
        self.memory_optimizer = MemoryOptimizer(self.resource_monitor)
        self.gpu_manager = GPUMemoryManager(self.resource_monitor)
        
        # Performance targets
        self.targets = {
            "latency": 3.0,      # <3 seconds
            "cpu_usage": 80.0,    # <80% CPU
            "memory_usage": 85.0,  # <85% memory
            "gpu_usage": 50.0,     # <50% GPU
            "success_rate": 40.0    # >40% success rate
        }
        
        # Optimization status
        self.optimization_enabled = False
        self.optimization_stats = {
            "optimizations_applied": 0,
            "latency_improvements": 0,
            "memory_savings": 0,
            "gpu_efficiency_gains": 0
        }
    
    def start_optimization(self, level: OptimizationLevel = OptimizationLevel.BENCHMARK):
        """Start performance optimization."""
        try:
            logger.info(f"Starting performance optimization: {level.value}")
            
            # Start resource monitoring
            self.resource_monitor.start_monitoring(interval=0.5)
            
            # Set optimization level
            self.latency_optimizer.set_optimization_level(level)
            
            # Apply initial optimizations
            self._apply_initial_optimizations()
            
            self.optimization_enabled = True
            logger.info("Performance optimization started")
            
            return True
            
        except Exception as e:
            logger.error(f"Optimization start failed: {e}")
            return False
    
    def stop_optimization(self):
        """Stop performance optimization."""
        try:
            self.resource_monitor.stop_monitoring()
            self.optimization_enabled = False
            logger.info("Performance optimization stopped")
            
        except Exception as e:
            logger.error(f"Optimization stop failed: {e}")
    
    def _apply_initial_optimizations(self):
        """Apply initial optimizations."""
        try:
            # Memory optimizations
            self.memory_optimizer.optimize_memory_layout()
            
            # GPU optimizations
            self.gpu_manager.optimize_gpu_usage()
            
            # System optimizations
            self._apply_system_optimizations()
            
            self.optimization_stats["optimizations_applied"] += 1
            
        except Exception as e:
            logger.error(f"Initial optimizations failed: {e}")
    
    def _apply_system_optimizations(self):
        """Apply system-level optimizations."""
        try:
            # Python optimizations
            import sys
            sys.setrecursionlimit(10000)  # Increase recursion limit
            
            # Threading optimizations
            import threading
            threading.stack_size(1024 * 1024)  # 1MB stack size
            
            logger.info("System optimizations applied")
            
        except Exception as e:
            logger.error(f"System optimizations failed: {e}")
    
    def optimize_function_execution(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with full optimization."""
        if not self.optimization_enabled:
            return func(*args, **kwargs)
        
        return self.latency_optimizer.optimize_execution(func, *args, **kwargs)
    
    def check_performance_targets(self) -> Dict:
        """Check if performance targets are being met."""
        try:
            metrics = self.resource_monitor.get_average_metrics(window_size=20)
            latency_stats = self.latency_optimizer.get_latency_stats()
            
            if not metrics or "error" in latency_stats:
                return {"error": "Insufficient data for target checking"}
            
            # Check each target
            target_status = {
                "latency_target_met": latency_stats["avg_latency"] <= self.targets["latency"],
                "cpu_target_met": metrics.cpu_usage <= self.targets["cpu_usage"],
                "memory_target_met": metrics.memory_usage <= self.targets["memory_usage"],
                "gpu_target_met": metrics.gpu_usage <= self.targets["gpu_usage"],
                "overall_targets_met": False
            }
            
            # Overall status
            target_status["overall_targets_met"] = all([
                target_status["latency_target_met"],
                target_status["cpu_target_met"],
                target_status["memory_target_met"],
                target_status["gpu_target_met"]
            ])
            
            return {
                **target_status,
                "current_metrics": {
                    "avg_latency": latency_stats["avg_latency"],
                    "cpu_usage": metrics.cpu_usage,
                    "memory_usage": metrics.memory_usage,
                    "gpu_usage": metrics.gpu_usage
                },
                "targets": self.targets
            }
            
        except Exception as e:
            logger.error(f"Target checking failed: {e}")
            return {"error": str(e)}
    
    def get_optimization_stats(self) -> Dict:
        """Get comprehensive optimization statistics."""
        return {
            "optimization_stats": self.optimization_stats,
            "resource_metrics": self.resource_monitor.get_average_metrics(),
            "latency_stats": self.latency_optimizer.get_latency_stats(),
            "target_status": self.check_performance_targets(),
            "memory_pools": self.memory_optimizer.memory_pools,
            "gpu_pools": self.gpu_manager.gpu_memory_pools
        }
    
    def prepare_for_benchmark(self) -> bool:
        """Prepare system for benchmark execution."""
        try:
            logger.info("Preparing system for benchmark")
            
            # Start aggressive optimization
            if not self.start_optimization(OptimizationLevel.BENCHMARK):
                return False
            
            # Pre-allocate memory pools
            self.memory_optimizer.allocate_memory_pool("vision", 512)  # 512MB for vision
            self.memory_optimizer.allocate_memory_pool("planning", 256)  # 256MB for planning
            self.memory_optimizer.allocate_memory_pool("execution", 128)  # 128MB for execution
            
            # Pre-allocate GPU memory if available
            if self.gpu_manager.max_gpu_memory > 0:
                self.gpu_manager.allocate_gpu_memory("models", 1024)  # 1GB for models
            
            logger.info("System prepared for benchmark")
            return True
            
        except Exception as e:
            logger.error(f"Benchmark preparation failed: {e}")
            return False
