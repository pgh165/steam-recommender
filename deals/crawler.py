import re
import time
import warnings
import requests
from django.utils import timezone
from library.models import Game, normalize_name
from deals.models import Deal


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _save_deal(game, platform, category, original_price, sale_price, discount_percent, deal_url):
    Deal.objects.update_or_create(
        game=game,
        platform=platform,
        defaults={
            'category': category,
            'original_price': original_price,
            'sale_price': sale_price,
            'discount_percent': discount_percent,
            'deal_url': deal_url,
            'fetched_at': timezone.now(),
        },
    )


# ── Steam ─────────────────────────────────────────────────────────────────────

def fetch_steam_deals():
    from library.steam_api import get_steam_deals, get_top100_app_ids

    count = 0

    # 1) specials / top_sellers (featuredcategories)
    items = get_steam_deals()
    for item in items:
        app_id = item.get('id')
        if not app_id:
            continue
        if _is_adult_content(app_id):
            time.sleep(0.3)
            continue

        name = item.get('name', '')
        thumbnail = item.get('header_image') or _steam_thumbnail(app_id)

        game, created = Game.objects.get_or_create(
            steam_app_id=app_id,
            defaults={'name': name, 'thumbnail_url': thumbnail},
        )
        update_fields = []
        if not created and item.get('header_image'):
            game.thumbnail_url = thumbnail
            update_fields.append('thumbnail_url')
        if not game.normalized_name:
            update_fields.append('normalized_name')
        if update_fields:
            game.save(update_fields=update_fields)

        # 한국어 이름 수집 (아직 없으면)
        if not game.korean_name:
            _fetch_korean_name(game)

        original = (item.get('original_price') or 0) / 100
        final = (item.get('final_price') or 0) / 100
        discount = item.get('discount_percent', 0)
        category = item.get('_category', 'specials')

        _save_deal(game, 'steam', category, original, final, discount,
                   f'https://store.steampowered.com/app/{app_id}/')
        count += 1
        time.sleep(0.3)

    # 2) SteamSpy top100 인기 게임 (popular 카테고리) — 판매량 + 평점 기록
    try:
        top100 = get_top100_app_ids()
    except Exception:
        top100 = []

    for app_id, name, positive, negative in top100:
        total_reviews = positive + negative
        if positive < 500:
            continue
        review_score = positive / total_reviews if total_reviews > 0 else 0.0
        if review_score < 0.8:
            continue

        try:
            detail_resp = requests.get(
                'https://store.steampowered.com/api/appdetails',
                params={'appids': app_id, 'cc': 'kr', 'filters': 'price_overview,basic,content_descriptors'},
                timeout=8,
            )
            detail_data = detail_resp.json().get(str(app_id), {})
            if not detail_data.get('success'):
                time.sleep(0.2)
                continue
            app_data = detail_data.get('data', {})
            if app_data.get('type') not in ('game', 'dlc', None, ''):
                time.sleep(0.2)
                continue
            required_age = int(app_data.get('required_age') or 0)
            descriptor_ids = app_data.get('content_descriptors', {}).get('ids', [])
            if required_age >= 18 or set(descriptor_ids) & {3, 4}:
                time.sleep(0.2)
                continue
            if app_data.get('is_free'):
                time.sleep(0.2)
                continue
            name = app_data.get('name', name)
            thumbnail = app_data.get('header_image') or _steam_thumbnail(app_id)
            price_ov = app_data.get('price_overview')
            if not price_ov:
                time.sleep(0.2)
                continue
            original = (price_ov.get('initial') or 0) / 100
            final = (price_ov.get('final') or 0) / 100
            discount = price_ov.get('discount_percent', 0)
        except Exception:
            time.sleep(0.2)
            continue

        game, created = Game.objects.get_or_create(
            steam_app_id=app_id,
            defaults={'name': name, 'thumbnail_url': thumbnail},
        )
        update_fields = []
        if not created and thumbnail and not game.thumbnail_url:
            game.thumbnail_url = thumbnail
            update_fields.append('thumbnail_url')
        if not game.normalized_name:
            update_fields.append('normalized_name')
        if game.review_score != review_score:
            game.review_score = review_score
            update_fields.append('review_score')
        if update_fields:
            game.save(update_fields=update_fields)

        # 한국어 이름 수집 (아직 없으면)
        if not game.korean_name:
            _fetch_korean_name(game)

        _save_deal(game, 'steam', 'popular', original, final, discount,
                   f'https://store.steampowered.com/app/{app_id}/')
        count += 1
        time.sleep(0.3)

    return count


def _fetch_korean_name(game):
    """Steam Store 한국어 appdetails로 게임의 한국어 이름 수집."""
    try:
        resp = requests.get(
            'https://store.steampowered.com/api/appdetails',
            params={'appids': game.steam_app_id, 'cc': 'kr', 'l': 'koreana', 'filters': 'basic'},
            timeout=6,
        )
        data = resp.json().get(str(game.steam_app_id), {})
        if not data.get('success'):
            return
        ko_name = data.get('data', {}).get('name', '')
        if ko_name and ko_name != game.name:
            game.korean_name = ko_name
            game.save(update_fields=['korean_name'])
    except Exception:
        pass


# ── 다이렉트게임즈 ────────────────────────────────────────────────────────────

def fetch_directgames_deals():
    """
    Steam 인기 게임 목록을 기준으로 다이렉트게임즈에서 역방향 검색.
    영어 이름 또는 한국어 이름으로 검색해 일치하는 딜만 저장.
    """
    from bs4 import BeautifulSoup

    BASE = 'https://directg.net'
    HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    session = requests.Session()
    session.verify = False
    warnings.filterwarnings('ignore', message='Unverified HTTPS')

    # Steam 딜이 있는 게임만 대상
    steam_games = list(
        Game.objects.filter(
            deals__platform='steam'
        ).exclude(steam_app_id=None).distinct()
    )

    count = 0
    for game in steam_games:
        # 영어 이름으로 먼저 검색, 없으면 한국어 이름으로
        search_terms = [game.name]
        if game.korean_name and game.korean_name != game.name:
            search_terms.append(game.korean_name)

        found = False
        for term in search_terms:
            if found:
                break
            try:
                r = session.get(
                    f'{BASE}/game/game_search_thumb.html',
                    params={'q': term},
                    headers=HEADERS, timeout=8,
                )
                soup = BeautifulSoup(r.text, 'html.parser')
            except Exception:
                time.sleep(0.2)
                continue

            for card in soup.select('.card.rounded-0.bg-card'):
                label_el = card.select_one('.label_area .label')
                if label_el and label_el.get_text(strip=True).upper() not in ('GAME', ''):
                    continue

                content = card.find_next_sibling()
                if not content:
                    continue

                name_el     = content.select_one('.product_name_area')
                discount_el = content.select_one('.discount-rate')
                orig_el     = content.select_one('.consumer_price s')
                sale_el     = content.select_one('.discount_price span')
                a           = card.select_one('a[href*="game_view"]')

                dg_name  = name_el.get_text(strip=True) if name_el else ''
                if not dg_name:
                    continue

                # 이름 유사도 검증: normalized 기준 포함 관계
                norm_dg   = normalize_name(dg_name)
                norm_game = normalize_name(game.name)
                norm_ko   = normalize_name(game.korean_name) if game.korean_name else ''

                match = (
                    norm_dg == norm_game or
                    norm_dg == norm_ko or
                    (norm_game and norm_game in norm_dg) or
                    (norm_ko and norm_ko in norm_dg) or
                    (norm_dg and norm_dg in norm_game) or
                    (norm_dg and norm_ko and norm_dg in norm_ko)
                )
                if not match:
                    continue

                discount = int(re.sub(r'[^\d]', '', discount_el.get_text() if discount_el else '') or 0)
                orig     = int(re.sub(r'[^\d]', '', orig_el.get_text() if orig_el else '') or 0)
                sale     = int(re.sub(r'[^\d]', '', sale_el.get_text() if sale_el else '') or 0)

                if sale == 0:
                    continue

                deal_url = BASE + a['href'] if a else ''
                _save_deal(game, 'directgames', 'specials', orig, sale, discount, deal_url)
                count += 1
                found = True
                break

            time.sleep(0.25)

    return count


# ── Steam 헬퍼 ───────────────────────────────────────────────────────────────

def _is_adult_content(app_id):
    try:
        resp = requests.get(
            'https://store.steampowered.com/api/appdetails',
            params={'appids': app_id, 'cc': 'kr', 'filters': 'content_descriptors,age_gate'},
            timeout=8,
        )
        data = resp.json().get(str(app_id), {})
        if not data.get('success'):
            return False
        app_data = data.get('data', {})
        required_age = int(app_data.get('required_age') or 0)
        descriptor_ids = app_data.get('content_descriptors', {}).get('ids', [])
        return required_age >= 18 or bool(set(descriptor_ids) & {3, 4})
    except Exception:
        return False


def _steam_thumbnail(app_id):
    return f'https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg'
