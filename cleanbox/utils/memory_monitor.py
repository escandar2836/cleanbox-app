"""
메모리 사용량 모니터링 유틸리티
Render 환경에서 메모리 사용량을 추적하고 제한을 관리합니다.
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
    """메모리 사용량 모니터링"""

    def __init__(self, max_memory_mb: int = 400):  # 512MB 중 400MB 사용
        self.max_memory_mb = max_memory_mb
        self.logger = logging.getLogger(__name__)
        self.warning_threshold = 0.8  # 80% 경고 임계값
        self.critical_threshold = 0.9  # 90% 위험 임계값

    def get_memory_usage(self) -> Dict:
        """현재 메모리 사용량 반환"""
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
            self.logger.warning(f"메모리 사용량 확인 실패: {str(e)}")
            return self._get_memory_usage_fallback()

    def _get_memory_usage_fallback(self) -> Dict:
        """psutil 없을 때의 대체 메서드"""
        return {
            "memory_mb": 0,
            "memory_percent": 0,
            "is_safe": True,  # 확인 불가시 안전하다고 가정
            "is_critical": False,
            "max_memory_mb": self.max_memory_mb,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "psutil_available": False,
        }

    def check_memory_limit(self) -> bool:
        """메모리 제한 체크"""
        usage = self.get_memory_usage()
        is_safe = usage["is_safe"]

        if not is_safe:
            self.logger.warning(
                f"메모리 사용량 위험: {usage['memory_mb']:.1f}MB ({usage['memory_percent']:.1f}%)"
            )

        if usage.get("is_critical", False):
            self.logger.error(
                f"메모리 사용량 위험 수준: {usage['memory_mb']:.1f}MB ({usage['memory_percent']:.1f}%)"
            )

        return is_safe

    def log_memory_usage(self, context: str = ""):
        """메모리 사용량 로깅"""
        usage = self.get_memory_usage()

        if usage.get("psutil_available", True):
            level = logging.INFO
            if usage.get("is_critical", False):
                level = logging.ERROR
            elif not usage.get("is_safe", True):
                level = logging.WARNING

            self.logger.log(
                level,
                f"메모리 사용량 ({context}): {usage['memory_mb']:.1f}MB ({usage['memory_percent']:.1f}%)",
            )
        else:
            self.logger.info(f"메모리 모니터링 불가 ({context})")

    def get_memory_stats(self) -> Dict:
        """메모리 통계 반환"""
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
        """정리 필요 여부 확인"""
        usage = self.get_memory_usage()
        return not usage.get("is_safe", True) or usage.get("is_critical", False)


# 전역 메모리 모니터 인스턴스
memory_monitor = MemoryMonitor()
