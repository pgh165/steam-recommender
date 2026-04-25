# 스팀 게임 할인 추천 서비스

사용자의 스팀 라이브러리를 분석하고 현재 할인 중인 게임 중 좋아할 만한 게임을 추천해주는 Django 웹 서비스입니다.

## 기술 스택

- **백엔드**: Django 4.x
- **AI 엔진**: Ollama (로컬 LLM, 기본 모델: `gemma4:8b`)
- **크롤링**: requests + BeautifulSoup4
- **외부 API**: Steam Web API, IsThereAnyDeal API
- **DB**: PostgreSQL 15
- **스케줄러**: django-crontab (할인 정보 주기적 갱신)
- **프론트엔드**: Django Templates + Vanilla JS

## 프로젝트 구조

```
steam_recommender/
├── CLAUDE.md
├── manage.py
├── requirements.txt
├── .env.example
├── config/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/
│   ├── models.py        # SteamUser 모델
│   ├── views.py         # 스팀 로그인 (Steam OpenID)
│   └── urls.py
├── library/
│   ├── models.py        # Game, UserGame 모델
│   ├── views.py         # 라이브러리 동기화
│   ├── steam_api.py     # Steam Web API 클라이언트
│   └── urls.py
├── deals/
│   ├── models.py        # Deal 모델
│   ├── views.py         # 할인 목록 페이지
│   ├── crawler.py       # 할인 정보 수집
│   └── management/
│       └── commands/
│           └── fetch_deals.py  # 크론잡용 커맨드
├── recommender/
│   ├── views.py         # 추천 결과 페이지
│   ├── ollama_client.py # Ollama API 클라이언트
│   └── prompt.py        # 추천 프롬프트 템플릿
└── templates/
    ├── base.html
    ├── accounts/
    │   └── login.html
    ├── library/
    │   └── library.html
    ├── deals/
    │   └── deals.html
    └── recommender/
        └── recommend.html
```

## 환경 변수 (.env)

```
STEAM_API_KEY=your_steam_api_key
ITAD_API_KEY=your_itad_api_key
SECRET_KEY=your_django_secret_key
DEBUG=True
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:8b
```

Steam API 키 발급: https://steamcommunity.com/dev/apikey
IsThereAnyDeal API 키 발급: https://isthereanydeal.com/dev/app/

## 구현 순서

### 1단계: 프로젝트 세팅

```bash
pip install django python-dotenv requests beautifulsoup4 django-crontab
django-admin startproject config .
python manage.py startapp accounts
python manage.py startapp library
python manage.py startapp deals
python manage.py startapp recommender
```

`requirements.txt`:
```
django>=4.2
python-dotenv
requests
beautifulsoup4
django-crontab
```

### 2단계: 모델 정의

**accounts/models.py** — SteamUser
```python
# SteamUser: user(OneToOne→User), steam_id(char), display_name, avatar_url, profile_updated_at
```

**library/models.py** — Game, UserGame
```python
# Game: steam_app_id(unique), name, genres(JSON), tags(JSON), thumbnail_url
# UserGame: user(FK→SteamUser), game(FK→Game), playtime_minutes, last_played
```

**deals/models.py** — Deal
```python
# Deal: game(FK→Game), platform(steam/gog/epic), original_price, sale_price,
#        discount_percent, deal_url, expires_at, fetched_at
```

### 3단계: Steam API 클라이언트 (library/steam_api.py)

함수 3개를 구현하세요.

**`get_owned_games(steam_id)`**
- 엔드포인트: `https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/`
- 파라미터: `key, steamid, include_appinfo=true, include_played_free_games=true`
- 반환: `[{appid, name, playtime_forever, img_icon_url}, ...]`

**`get_app_details(app_id)`**
- 엔드포인트: `https://store.steampowered.com/api/appdetails?appids={app_id}&cc=kr&l=korean`
- 반환: 게임 장르, 태그, 설명 등 상세 정보

**`get_steam_deals()`**
- 엔드포인트: `https://store.steampowered.com/api/featuredcategories`
- 현재 스팀 특가 게임 목록 반환

### 4단계: 할인 정보 크롤러 (deals/crawler.py)

함수 2개를 구현하세요.

**`fetch_itad_deals()`**
IsThereAnyDeal API로 현재 할인 중인 게임 수집.
- 엔드포인트: `https://api.isthereanydeal.com/deals/v2`
- 파라미터: `key, limit=100, sort=cut` (할인율 높은 순)
- 결과를 Deal 모델에 저장 (upsert 방식)

**`fetch_steam_deals()`**
Steam 특가 페이지에서 할인 게임 크롤링.
- `get_steam_deals()` 함수 활용
- 스팀 전용 할인 정보를 Deal 모델에 저장

**management command (deals/management/commands/fetch_deals.py)**
```python
# python manage.py fetch_deals 실행 시
# fetch_itad_deals() + fetch_steam_deals() 순서로 실행
# 완료 후 "총 N개 할인 정보 업데이트 완료" 출력
```

### 5단계: 라이브러리 동기화 뷰 (library/views.py)

**`sync_library(request)`** (POST)
- 로그인한 유저의 steam_id로 `get_owned_games()` 호출
- 결과를 Game + UserGame 모델에 저장 (upsert)
- 플레이타임 기준 상위 20개 게임은 `get_app_details()`로 장르/태그 추가 수집
- 완료 후 라이브러리 페이지로 redirect

**`library(request)`** (GET)
- 유저의 UserGame 목록을 플레이타임 내림차순으로 조회
- `library/library.html` 렌더링

### 6단계: Ollama 클라이언트 (recommender/ollama_client.py)

**`get_recommendation(user_games, deals)`**
- `user_games`: 플레이타임 상위 10개 게임 (이름 + 플레이타임 + 장르)
- `deals`: 현재 할인 중인 게임 목록 (이미 보유한 게임 제외, 최대 30개)
- Ollama `/api/chat` 호출 후 추천 결과 텍스트 반환

### 7단계: 추천 프롬프트 (recommender/prompt.py)

`build_prompt(user_games, deals)` 함수를 구현하세요.

```
당신은 게임 추천 전문가입니다. 사용자의 플레이 기록을 분석해서 현재 할인 중인 게임 중 가장 잘 맞는 게임을 추천해주세요.

[사용자 플레이 기록]
{user_games_text}

[현재 할인 중인 게임]
{deals_text}

위 정보를 바탕으로:
1. 사용자가 좋아하는 장르/스타일을 분석해주세요.
2. 할인 게임 중 잘 맞는 게임 3개를 추천하고, 각각 왜 이 사람에게 맞는지 설명해주세요.
3. 추천 형식: 게임명 | 할인가 | 추천 이유 (2줄 이내)

한국어로 답변해주세요.
```

### 8단계: 추천 뷰 (recommender/views.py)

**`recommend(request)`** (GET)
1. 로그인 유저의 UserGame을 플레이타임 내림차순 상위 10개 조회
2. 현재 Deal 목록에서 유저가 보유하지 않은 게임만 필터링 (최대 30개)
3. `build_prompt()` → `get_recommendation()` 호출
4. 결과를 `recommender/recommend.html`에 렌더링
5. 추천 결과는 세션에 캐싱 (같은 날 재요청 시 Ollama 재호출 방지)

### 9단계: URL 설정

`config/urls.py`:
```python
path('', include('accounts.urls'))
path('library/', include('library.urls'))
path('deals/', include('deals.urls'))
path('recommend/', include('recommender.urls'))
```

각 앱 urls.py:
```python
# accounts: path('login/', ...), path('logout/', ...)
# library: path('', library), path('sync/', sync_library)
# deals: path('', deals_list)
# recommender: path('', recommend)
```

### 10단계: 스팀 로그인 (accounts/views.py)

Steam OpenID를 사용한 로그인을 구현하세요.

- 로그인 버튼 클릭 시 Steam 로그인 페이지로 redirect
- Steam 인증 완료 후 콜백 URL로 steam_id 수신
- SteamUser 모델에 저장 후 Django 세션 생성
- Steam OpenID 엔드포인트: `https://steamcommunity.com/openid/login`

간단 구현을 원하면 Steam OpenID 대신 **Steam ID 직접 입력** 방식도 가능:
```
입력창에 Steam ID 또는 프로필 URL 입력 → 파싱 → 라이브러리 조회
```

### 11단계: 템플릿

**base.html**
- 네비게이션: 로고, 내 라이브러리, 할인 목록, 추천받기
- 다크 테마 (게임 서비스 분위기)

**library/library.html**
- 게임 목록 (썸네일 + 이름 + 플레이타임)
- "라이브러리 동기화" 버튼
- 플레이타임 기준 정렬

**deals/deals.html**
- 할인 게임 카드 (썸네일, 원가, 할인가, 할인율)
- 플랫폼 필터 (Steam / GOG / Epic)
- 마지막 업데이트 시각 표시

**recommender/recommend.html**
- 사용자 플레이 성향 요약
- 추천 게임 3개 카드
- "다시 추천받기" 버튼

## Docker 구성

### 컨테이너 구조
```
docker-compose
├── web       # Django 앱 (포트 8000)
├── ollama    # Ollama LLM 서버 (포트 11434)
└── db        # PostgreSQL 15 (포트 5432)
```

### Dockerfile (프로젝트 루트)
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 정적 파일 수집
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### docker-compose.yml (프로젝트 루트)
```yaml
version: '3.9'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: steam_recommender
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  web:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/steam_recommender
      - OLLAMA_BASE_URL=http://ollama:11434
    depends_on:
      - db
      - ollama
    volumes:
      - .:/app  # 개발 중 코드 변경 즉시 반영

volumes:
  postgres_data:
  ollama_data:
```

### .env.example 수정 (PostgreSQL 반영)
```
STEAM_API_KEY=your_steam_api_key
ITAD_API_KEY=your_itad_api_key
SECRET_KEY=your_django_secret_key
DEBUG=True
DATABASE_URL=postgresql://postgres:postgres@db:5432/steam_recommender
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=gemma4:8b
```

### settings.py DB 설정 변경
PostgreSQL을 사용하도록 settings.py를 아래와 같이 설정하세요.
```python
import os
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600
    )
}
```
requirements.txt에 `dj-database-url`, `psycopg2-binary` 추가 필요.

## 실행 방법

```bash
# 환경 설정
cp .env.example .env
# .env에 API 키 입력

# 컨테이너 빌드 및 실행
docker compose up --build

# (최초 1회) Ollama 모델 다운로드 - 별도 터미널에서
docker compose exec ollama ollama pull gemma4:8b

# (최초 1회) DB 마이그레이션
docker compose exec web python manage.py migrate

# 할인 정보 초기 수집
docker compose exec web python manage.py fetch_deals
```

### 자주 쓰는 명령어
```bash
# 컨테이너 상태 확인
docker compose ps

# Django 로그 확인
docker compose logs web -f

# Ollama 로그 확인
docker compose logs ollama -f

# 마이그레이션
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# 할인 정보 수동 갱신
docker compose exec web python manage.py fetch_deals

# 컨테이너 종료
docker compose down

# 볼륨까지 삭제 (DB 초기화)
docker compose down -v
```

## 완성 체크리스트

- [ ] Django 프로젝트 세팅 및 앱 4개 생성
- [ ] 모델 정의 및 마이그레이션 (SteamUser, Game, UserGame, Deal)
- [ ] Steam API로 라이브러리 수집
- [ ] IsThereAnyDeal API로 할인 정보 수집
- [ ] 할인 정보 자동 갱신 management command
- [ ] Ollama 연동 및 추천 프롬프트
- [ ] 추천 결과 페이지 렌더링
- [ ] Steam ID 입력 방식 구현 (로그인 불필요)
- [ ] 다크 테마 UI
- [ ] 보유 게임 제외 필터링 정상 동작
- [ ] 추천 결과 세션 캐싱

## 주의사항

### Steam 라이브러리 비공개 처리
사용자 프로필이 비공개면 API가 빈 배열을 반환함.
`get_owned_games()` 결과가 비어있으면 "프로필을 공개로 설정해주세요" 안내 필요.

### 컨텍스트 길이 관리
할인 게임 전체를 LLM에 넘기지 말 것.
장르 기반으로 사전 필터링 후 최대 30개만 전달.

### API Rate Limit
Steam API는 하루 100,000 요청 제한 있음.
게임 상세 정보 수집 시 요청 사이에 0.5~1초 딜레이 추가.
```python
import time
time.sleep(0.5)
```

## 다중 사용자 지원

### Steam ID 입력 방식
로그인 없이 Steam ID만 입력하면 누구나 사용 가능한 구조로 구현하세요.

**흐름**
```
메인 페이지 → Steam ID 입력 → 라이브러리 조회 → 추천 결과
```

**accounts/views.py 구현**
```python
# Steam ID 입력 폼 처리
def index(request):
    if request.method == 'POST':
        steam_id = request.POST.get('steam_id', '').strip()
        # 커스텀 URL 입력 시 숫자 ID로 변환
        # https://steamcommunity.com/id/닉네임 → steamid.io API로 변환
        request.session['steam_id'] = steam_id
        return redirect('library')
    return render(request, 'accounts/index.html')
```

**커스텀 URL → Steam ID 변환**
사용자가 숫자 ID 대신 프로필 URL을 입력할 수 있도록 변환 로직 추가.
```python
def resolve_steam_id(input_str):
    # 숫자로만 이루어진 경우 그대로 반환
    if input_str.isdigit():
        return input_str
    # 커스텀 URL에서 닉네임 추출 후 API로 변환
    # https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/
    vanity = input_str.rstrip('/').split('/')[-1]
    res = requests.get(
        'https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/',
        params={'key': STEAM_API_KEY, 'vanityurl': vanity}
    )
    data = res.json()
    if data['response']['success'] == 1:
        return data['response']['steamid']
    return None
```

**세션 기반 사용자 구분**
Django 세션에 steam_id를 저장해서 각 사용자의 데이터를 분리.
```python
# 모든 뷰에서 세션으로 steam_id 접근
steam_id = request.session.get('steam_id')
if not steam_id:
    return redirect('index')
```

**UserGame 모델에 steam_id 필드 추가**
여러 사용자의 데이터를 함께 저장할 수 있도록 steam_id 기준으로 조회.
```python
# UserGame 조회 시
user_games = UserGame.objects.filter(steam_id=steam_id).order_by('-playtime_minutes')
```

### 주의사항
- Steam API 키는 서버에만 보관, 사용자에게 노출 금지
- 라이브러리 캐싱: 같은 Steam ID 재요청 시 DB에 저장된 데이터 반환 (API 절약)
- 캐시 만료: `library_updated_at` 필드로 24시간 지난 경우만 재동기화