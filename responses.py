"""
서비스 계층 응답 빌더

모든 서비스는 아래 두 형태 중 하나의 dict를 반환한다.

성공: {"success": True, "message": str, ...추가 데이터}
실패: {"success": False, "error_code": str, "message": str, ...추가 데이터}

추가 데이터는 중첩하지 않고 최상위에 펼쳐 담는다.
핸들러가 `result["quantity"]`처럼 바로 꺼내 쓰기 때문이다.
"""

from typing import Dict


def success_response(message: str = "성공", **data) -> Dict:
    """성공 응답 생성"""
    response = {"success": True, "message": message}
    response.update(data)
    return response


def error_response(error_code: str, message: str, **extra_data) -> Dict:
    """에러 응답 생성"""
    response = {"success": False, "error_code": error_code, "message": message}
    if extra_data:
        response.update(extra_data)
    return response
