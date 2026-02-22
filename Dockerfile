# ===========================================
# 주식왕 카카오봇 - Docker 이미지
# 멀티스테이지 빌드로 최소 이미지 크기 유지
# ===========================================

# Stage 1: 빌드
FROM python:3.11-slim AS builder

# 빌드 의존성 설치 (psycopg2-binary 컴파일 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성만 먼저 설치 (레이어 캐싱 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===========================================
# Stage 2: 런타임
# ===========================================
FROM python:3.11-slim AS runtime

# 보안: 루트가 아닌 사용자로 실행
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 런타임 의존성 (psycopg2-binary 런타임 라이브러리)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 빌드 스테이지에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

# 애플리케이션 코드 복사
COPY --chown=appuser:appuser . .

# 로그 디렉토리 생성
RUN mkdir -p logs && chown appuser:appuser logs

# 비루트 사용자로 전환
USER appuser

# 포트 노출
EXPOSE 8000

# 환경변수 기본값
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_DIR=/app/logs

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# 실행 명령
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
