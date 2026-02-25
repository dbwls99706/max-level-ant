"""
로깅 유틸리티
- 표준화된 로깅 시스템
"""
import logging
import sys


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    표준화된 로거 설정

    Args:
        name: 로거 이름 (보통 __name__)
        level: 로깅 레벨

    Returns:
        설정된 Logger 인스턴스
    """
    logger = logging.getLogger(name)

    # 이미 핸들러가 있으면 중복 추가 방지
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 콘솔 핸들러
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # 포맷 설정
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False  # 루트 로거로 전파 방지 (중복 출력 방지)

    return logger


# 루트 로거 설정
def configure_root_logger(level: int = logging.INFO) -> None:
    """루트 로거 설정 (앱 시작 시 호출)"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


# 미리 정의된 로거들
def get_main_logger() -> logging.Logger:
    """메인 앱 로거"""
    return setup_logger("stock_king.main")


def get_handler_logger() -> logging.Logger:
    """핸들러 로거"""
    return setup_logger("stock_king.handler")


def get_service_logger() -> logging.Logger:
    """서비스 로거"""
    return setup_logger("stock_king.service")


def get_api_logger() -> logging.Logger:
    """외부 API 로거"""
    return setup_logger("stock_king.api")
