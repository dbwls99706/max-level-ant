"""
API 응답 형식
"""

from typing import Any, Dict, Optional


class ApiResponse:
    """표준화된 API 응답 형식"""

    @staticmethod
    def success(data: Optional[Dict] = None, message: str = "성공") -> Dict[str, Any]:
        """성공 응답"""
        return {"success": True, "message": message, "data": data or {}}

    @staticmethod
    def error(
        error_code: str, message: str, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """에러 응답"""
        return {
            "success": False,
            "error_code": error_code,
            "message": message,
            "data": data or {},
        }
