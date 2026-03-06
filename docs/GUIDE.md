# 만렙개미 카카오톡 봇 - 개발 가이드

## 목차
1. [사전 준비물](#1-사전-준비물)
2. [STEP 1: 카카오톡 채널 만들기](#step-1-카카오톡-채널-만들기)
3. [STEP 2: 챗봇 관리자센터 신청](#step-2-챗봇-관리자센터-신청)
4. [STEP 3: 스킬 서버 개발](#step-3-스킬-서버-개발)
5. [STEP 4: 서버 배포 (Railway)](#step-4-서버-배포-railway)
6. [STEP 5: 챗봇 설정 및 연동](#step-5-챗봇-설정-및-연동)
7. [STEP 6: 테스트 및 배포](#step-6-테스트-및-배포)

---

## 1. 사전 준비물

### 필수 계정
- [ ] **카카오 계정** (카카오톡 사용 중이면 있음)
- [ ] **GitHub 계정** (https://github.com 에서 가입)
- [ ] **Railway 계정** (https://railway.app 에서 GitHub로 가입)

### 개발 환경
- [ ] Python 3.11 이상 설치
- [ ] Git 설치
- [ ] VS Code 또는 아무 코드 에디터

### 예상 소요 시간
- 카카오톡 채널 생성: 5분
- OBT 승인 대기: 3~5일 (개인 기준)
- 스킬 서버 개발: 2~3시간
- 배포 및 연동: 1시간

---

## STEP 1: 카카오톡 채널 만들기

### 1-1. 카카오톡 채널 관리자센터 접속
1. https://center.kakao.com 접속
2. 카카오 계정으로 로그인

### 1-2. 새 채널 만들기
1. 우측 상단 **[+ 새 채널 만들기]** 클릭
2. 채널 정보 입력:
   - **채널 이름**: `만렙개미` (원하는 이름)
   - **검색용 아이디**: `manlvgaemi` (영문, 고유해야 함)
   - **카테고리**: 게임 > 기타
   - **프로필 사진**: 아무 이미지 (나중에 변경 가능)

3. **[채널 개설]** 클릭

### 1-3. 채널 URL 확인
1. 좌측 메뉴에서 **[채널 홍보]** 클릭
2. **채널 URL** 복사해두기 (예: `https://pf.kakao.com/_xxxxx`)

   이 URL은 다음 단계에서 필요합니다.

---

## STEP 2: 챗봇 관리자센터 신청

### 2-1. OBT(오픈베타) 신청
1. https://chatbot.kakao.com 접속
2. 카카오 계정으로 로그인
3. **[OBT 참여 신청]** 버튼 클릭
4. 신청 정보 입력:
   - **신청 유형**: 개인 (기업보다 승인 빠름)
   - **채널 URL**: STEP 1에서 복사한 URL 붙여넣기
   - **신청 사유**: "가상 주식 투자 교육용 게임 챗봇 개발"

5. **[신청하기]** 클릭

### 2-2. 승인 대기
- 개인: 보통 3~5 영업일
- 승인되면 이메일 알림 옴
- 승인 전에 스킬 서버 개발을 먼저 진행!

---

## STEP 3: 스킬 서버 개발

### 3-1. 프로젝트 구조

```
stock-king-bot/
├── main.py                  # FastAPI 메인 서버
├── config.py                # 설정 (게임 밸런스, 각성, 메시지 등)
├── database.py              # DB 연결 + 마이그레이션
├── models.py                # DB 모델 (10개 테이블)
├── requirements.txt         # 패키지 목록
├── Dockerfile               # Docker 빌드
├── Procfile                 # Railway 배포용
├── handlers/                # 명령어 처리
│   ├── command_handler.py   # 명령어 라우팅 + 기본 핸들러
│   ├── base_handler.py      # 공통 유틸리티 믹스인
│   ├── trading_handler.py   # 매수/매도/포트폴리오
│   ├── game_handler.py      # 보물상자/시장예측/업다운/각성
│   ├── market_handler.py    # 시세/급등/급락/뉴스/검색
│   └── social_handler.py    # 랭킹/배틀/챌린지/마일스톤
├── services/                # 비즈니스 로직
│   ├── common.py            # safe_add/subtract, 공통 유틸
│   ├── user_service.py      # 유저 관리 + 출석
│   ├── stock_service.py     # KIS API 연동 + 시세 조회
│   ├── trade_service.py     # 거래 처리
│   ├── game_service.py      # 예측게임 로직
│   ├── enhance_service.py   # 각성(강화) 시스템
│   ├── ranking_service.py   # 랭킹 조회
│   ├── battle_service.py    # PvP 배틀
│   ├── news_service.py      # 뉴스 서비스
│   ├── mission_service.py   # 일간 미션
│   ├── challenge_service.py # 주간 챌린지
│   ├── milestone_service.py # 마일스톤
│   └── asset_service.py     # 자산 히스토리
├── utils/                   # 유틸리티
│   ├── kakao_response.py    # 카카오 응답 포맷
│   ├── visual_helpers.py    # 시각적 표현 헬퍼
│   ├── logger.py            # 로깅 설정
│   └── audit_logger.py      # 감사 로그
└── tests/                   # 테스트
    ├── conftest.py
    ├── test_trade_service.py
    ├── test_game_service.py
    ├── test_user_service.py
    ├── test_mission_service.py
    ├── test_enhance_service.py
    ├── test_common.py
    └── test_circuit_breaker.py
```

### 3-2. 로컬 개발 환경 설정

```bash
# 1. 프로젝트 폴더 생성
mkdir stock-king-bot
cd stock-king-bot

# 2. 가상환경 생성 및 활성화
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# 3. 필요 패키지 설치
pip install -r requirements.txt
```

### 3-3. 로컬 테스트

```bash
# 서버 실행
uvicorn main:app --reload --port 8000

# 테스트 URL
# http://localhost:8000/docs 에서 API 문서 확인 가능
# http://localhost:8000/health 에서 서버 상태 확인
```

---

## STEP 4: 서버 배포 (Railway)

### 4-1. GitHub 저장소 생성
1. https://github.com 접속
2. 우측 상단 **[+]** > **[New repository]**
3. Repository name: `stock-king-bot`
4. **[Create repository]** 클릭

### 4-2. 코드 업로드
```bash
# 프로젝트 폴더에서 실행
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/[사용자명]/stock-king-bot.git
git push -u origin main
```

### 4-3. Railway 배포
1. https://railway.app 접속
2. GitHub 계정으로 로그인
3. **[New Project]** > **[Deploy from GitHub repo]**
4. `stock-king-bot` 저장소 선택
5. **[Deploy Now]** 클릭

### 4-4. 환경 변수 설정
Railway 대시보드에서:
1. 프로젝트 클릭 > **[Variables]** 탭
2. 다음 환경 변수 추가:
   ```
   DATABASE_URL=postgresql://... (자동 생성됨)
   KIS_APP_KEY=your_app_key
   KIS_APP_SECRET=your_app_secret
   ```

### 4-5. 도메인 확인
1. **[Settings]** > **[Networking]**
2. **[Generate Domain]** 클릭
3. 생성된 URL 복사 (예: `https://stock-king-bot-production.up.railway.app`)

   이 URL이 스킬 서버 URL입니다!

---

## STEP 5: 챗봇 설정 및 연동

### 5-1. 챗봇 생성 (OBT 승인 후)
1. https://chatbot.kakao.com 접속
2. 우측 상단 **[+ 봇 만들기]** > **[카카오톡 챗봇]**
3. 봇 이름: `만렙개미`
4. **[확인]** 클릭

### 5-2. 스킬 등록
1. 좌측 메뉴 **[스킬]** 클릭
2. **[생성]** 버튼 클릭
3. 스킬 정보 입력:
   - **스킬명**: `만렙개미 스킬`
   - **URL**: `https://[Railway URL]/skill`
     (예: `https://stock-king-bot-production.up.railway.app/skill`)
   - **기본 스킬로 지정**: 체크

4. **[저장]** 클릭

### 5-3. 폴백 블록 설정
1. 좌측 메뉴 **[시나리오]** > **[기본 시나리오]** > **[폴백 블록]**
2. **[파라미터 설정]** 영역에서:
   - **스킬 선택**: 방금 만든 `만렙개미 스킬` 선택
3. **[봇 응답]** 영역에서:
   - **[스킬데이터로 사용]** 선택
4. **[저장]** 클릭

### 5-4. 웰컴 블록 설정 (선택)
1. **[시나리오]** > **[기본 시나리오]** > **[웰컴 블록]**
2. **[봇 응답]** 추가:
   ```
   만렙개미에 오신 것을 환영합니다!
   쪼렙 개미에서 만렙 개미로 성장하세요!

   /시작 - 게임 시작하기
   /도움말 - 명령어 보기
   ```
3. **[저장]** 클릭

### 5-5. 카카오톡 채널 연결
1. 좌측 메뉴 **[설정]** > **[카카오톡 채널 연결]**
2. STEP 1에서 만든 채널 선택
3. **[연결]** 클릭

---

## STEP 6: 테스트 및 배포

### 6-1. 봇 테스트
1. 좌측 메뉴 **[봇 테스트]** 클릭
2. 테스트 창에서 명령어 입력해보기:
   - `/시작`
   - `/출석`
   - `/시세 삼성전자`
   - `/각성`
   - `/랭킹`

### 6-2. 배포
1. 좌측 메뉴 **[배포]** 클릭
2. 우측 상단 **[배포]** 버튼 클릭
3. 배포 완료 메시지 확인

### 6-3. 실제 테스트
1. 카카오톡 앱 열기
2. 상단 검색에서 `만렙개미` (채널 이름) 검색
3. 채널 추가 후 채팅 시작
4. `/시작` 입력해서 테스트!

---

## 자주 발생하는 문제 & 해결법

### Q1. 스킬 서버 연결 실패
**증상**: "스킬 서버와 통신할 수 없습니다"
**해결**:
1. Railway 서버가 실행 중인지 확인
2. URL 끝에 `/skill` 붙었는지 확인
3. HTTPS인지 확인 (HTTP 안됨)

### Q2. 5초 타임아웃 오류
**증상**: 응답이 늦어서 오류 발생
**해결**:
1. KIS API 시세 캐시(60초)가 정상 작동하는지 확인
2. DB 커넥션 풀 설정 확인
3. 서킷 브레이커가 열린 상태인지 로그 확인

### Q3. 봇이 응답하지 않음
**증상**: 메시지 보내도 반응 없음
**해결**:
1. 챗봇이 배포되었는지 확인
2. 채널과 챗봇이 연결되었는지 확인
3. Railway 로그에서 에러 확인
4. `/health` 엔드포인트로 서버 상태 확인

---

## 참고 링크

- **카카오 챗봇 공식 문서**: https://kakaobusiness.gitbook.io/main/tool/chatbot
- **Railway 문서**: https://docs.railway.app
- **KIS OpenAPI**: https://apiportal.koreainvestment.com

---

## 다음 단계

모든 설정이 완료되면:
1. 친구들에게 채널 공유
2. 그룹 챗봇(팀채팅) 확장 - docs/GROUP_CHATBOT_GUIDE.md 참고
3. 기능 추가 (AI 분석, 시즌제, 해외 주식 등)
