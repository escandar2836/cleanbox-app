"""
Memory usage monitoring utility
Tracks and manages memory usage in Render environment.
"""

import os
import logging
from typing import Dict, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class MemoryMonitor:
    """Memory usage monitoring"""

    def __init__(self, max_memory_mb: int = 400):  # Use 400MB out of 512MB
        self.max_memory_mb = max_memory_mb
        self.logger = logging.getLogger(__name__)
        self.warning_threshold = 0.8  # 80% warning threshold
        self.critical_threshold = 0.9  # 90% critical threshold

    def get_memory_usage(self) -> Dict:
        """Return current memory usage"""
        if not PSUTIL_AVAILABLE:
            return self._get_memory_usage_fallback()

        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            memory_percent = (memory_mb / self.max_memory_mb) * 100
            is_safe = memory_mb < self.max_memory_mb * self.warning_threshold
            is_critical = memory_mb > self.max_memory_mb * self.critical_threshold

            return {
                "memory_mb": memory_mb,
                "memory_percent": memory_percent,
                "is_safe": is_safe,
                "is_critical": is_critical,
                "max_memory_mb": self.max_memory_mb,
                "warning_threshold": self.warning_threshold,
                "critical_threshold": self.critical_threshold,
            }
        except Exception as e:
            self.logger.warning(f"Failed to check memory usage: {str(e)}")
            return self._get_memory_usage_fallback()

    def _get_memory_usage_fallback(self) -> Dict:
        """Fallback method when psutil is not available"""
        return {
            "memory_mb": 0,
            "memory_percent": 0,
            "is_safe": True,  # Assume safe if cannot check
            "is_critical": False,
            "max_memory_mb": self.max_memory_mb,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "psutil_available": False,
        }

    def check_memory_limit(self) -> bool:
        """Check memory limit"""
        usage = self.get_memory_usage()
        is_safe = usage["is_safe"]

        if not is_safe:
            self.logger.warning(
                f"Memory usage warning: {usage['memory_mb']:.1f}MB ({usage['memory_percent']:.1f}%)"
            )

        if usage.get("is_critical", False):
            self.logger.error(
                f"Memory usage critical: {usage['memory_mb']:.1f}MB ({usage['memory_percent']:.1f}%)"
            )

        return is_safe

    def log_memory_usage(self, context: str = ""):
        """Log memory usage"""
        usage = self.get_memory_usage()

        if usage.get("psutil_available", True):
            level = logging.INFO
            if usage.get("is_critical", False):
                level = logging.ERROR
            elif not usage.get("is_safe", True):
                level = logging.WARNING

            self.logger.log(
                level,
                f"Memory usage ({context}): {usage['memory_mb']:.1f}MB ({usage['memory_percent']:.1f}%)",
            )
        else:
            self.logger.info(f"Memory monitoring unavailable ({context})")

    def get_memory_stats(self) -> Dict:
        """Return memory stats"""
        usage = self.get_memory_usage()
        return {
            "current_mb": usage["memory_mb"],
            "current_percent": usage["memory_percent"],
            "max_mb": usage["max_memory_mb"],
            "is_safe": usage["is_safe"],
            "is_critical": usage.get("is_critical", False),
            "psutil_available": usage.get("psutil_available", True),
        }

    def should_cleanup(self) -> bool:
        """Check if cleanup is needed"""
        usage = self.get_memory_usage()
        return not usage.get("is_safe", True) or usage.get("is_critical", False)


# Global memory monitor instance
memory_monitor = MemoryMonitor()
