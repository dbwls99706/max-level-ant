"""
주식왕 카카오톡 챗봇 - 메인 서버
"""
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
from contextlib import asynccontextmanager

from database import get_db, init_db
from handlers import CommandHandler
from utils import KakaoResponse
from services.stock_service import KISAPIClient


# ===========================================
# 앱 생명주기 관리
# ===========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    # 시작 시
    print("🚀 주식왕 봇 서버 시작!")
    init_db()  # DB 테이블 생성

    # KIS API 토큰 미리 발급 (타임아웃 방지)
    token = KISAPIClient.get_access_token()
    if token:
        print("✅ KIS API 토큰 준비 완료!")
    else:
        print("⚠️ KIS API 토큰 발급 실패 - 환경변수 확인 필요")

    yield
    # 종료 시
    print("👋 주식왕 봇 서버 종료!")


# ===========================================
# FastAPI 앱 생성
# ===========================================
app = FastAPI(
    title="주식왕 카카오톡 챗봇",
    description="가상 주식 투자 게임 챗봇 API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정 (필요시)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================
# 헬스체크 엔드포인트
# ===========================================
@app.get("/")
async def root():
    """서버 상태 확인"""
    return {
        "status": "ok",
        "message": "주식왕 봇 서버가 실행 중입니다!",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """헬스체크"""
    return {"status": "healthy"}


# ===========================================
# 카카오 스킬 엔드포인트
# ===========================================
@app.post("/skill")
async def kakao_skill(request: Request, db: Session = Depends(get_db)):
    """
    카카오톡 챗봇 스킬 엔드포인트
    
    카카오 챗봇 관리자센터에서 이 URL을 스킬 서버로 등록합니다.
    예: https://your-domain.com/skill
    """
    try:
        # 요청 파싱
        body = await request.json()
        
        # 유저 정보 추출
        user_request = body.get("userRequest", {})
        user_info = user_request.get("user", {})
        kakao_id = user_info.get("id", "")
        utterance = user_request.get("utterance", "")

        # 닉네임 추출 (카카오 OpenBuilder에서 제공)
        nickname = user_info.get("properties", {}).get("nickname", "")

        # 디버그: 카카오에서 받은 유저 정보 로그
        print(f"📥 카카오 유저 정보: {user_info}")
        print(f"📥 닉네임: '{nickname}'")

        # 유저 ID 없으면 에러
        if not kakao_id:
            return KakaoResponse.simple_text("유저 정보를 확인할 수 없습니다.")

        # 명령어 처리
        handler = CommandHandler(db, kakao_id, utterance, nickname)
        response = handler.handle()
        
        return response
        
    except Exception as e:
        print(f"❌ 스킬 처리 에러: {e}")
        import traceback
        traceback.print_exc()
        
        return KakaoResponse.simple_text(
            "죄송합니다. 오류가 발생했습니다.\n잠시 후 다시 시도해주세요."
        )


# ===========================================
# 디버그용 엔드포인트
# ===========================================
@app.post("/debug/skill")
async def debug_skill(request: Request, db: Session = Depends(get_db)):
    """
    디버그용 스킬 테스트 엔드포인트
    
    curl로 테스트:
    curl -X POST http://localhost:8000/debug/skill \
         -H "Content-Type: application/json" \
         -d '{"kakao_id": "test123", "message": "/시작"}'
    """
    try:
        body = await request.json()
        kakao_id = body.get("kakao_id", "test_user")
        message = body.get("message", "/도움말")
        
        handler = CommandHandler(db, kakao_id, message)
        response = handler.handle()
        
        return response
        
    except Exception as e:
        return {"error": str(e)}


# ===========================================
# 메인 실행
# ===========================================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # 개발 시 자동 리로드
    )
