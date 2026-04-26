import re
import json
from datetime import date
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from library.models import UserGame, Game, normalize_name
from deals.models import Deal
from .ollama_client import get_recommendation, chat_with_context


def _build_system_context(user_games_data, deals_data):
    from recommender.prompt import build_prompt
    return build_prompt(user_games_data, deals_data)


def _parse_recommended_games(result_text):
    """AI 응답에서 [게임명] 패턴을 추출해 DB 정보와 함께 반환."""
    names = re.findall(r'\[([^\]]+)\]', result_text)
    cards = []
    seen = set()
    for raw_name in names[:3]:
        if raw_name in seen:
            continue
        seen.add(raw_name)
        norm = normalize_name(raw_name)
        game = None
        if norm:
            game = Game.objects.filter(normalized_name=norm).exclude(steam_app_id=None).first()
        if not game:
            game = Game.objects.filter(name__icontains=raw_name[:20]).exclude(steam_app_id=None).first()
        if not game or not game.steam_app_id:
            continue
        deal = Deal.objects.filter(game=game, platform='steam').first()
        dg_deal = Deal.objects.filter(game=game, platform='directgames').first()
        cards.append({
            'name': game.name,
            'steam_app_id': game.steam_app_id,
            'thumbnail_url': f'https://cdn.akamai.steamstatic.com/steam/apps/{game.steam_app_id}/header.jpg',
            'steam_url': f'https://store.steampowered.com/app/{game.steam_app_id}/',
            'detail_url': f'/deals/game/{game.steam_app_id}/',
            'youtube_url': f'https://www.youtube.com/results?search_query={game.name.replace(" ", "+")}+게임+트레일러',
            'sale_price': float(deal.sale_price) if deal and deal.sale_price else None,
            'original_price': float(deal.original_price) if deal and deal.original_price else None,
            'discount_percent': deal.discount_percent if deal else 0,
            'has_directgames': dg_deal is not None,
            'review_score': round(game.review_score * 100) if game.review_score else None,
            'genres': game.genres,
        })
    return cards


@login_required(login_url='login')
def recommend(request):
    steam_user = request.user.steam_profile
    today = str(date.today())
    cache_key = f'recommendation_{steam_user.steam_id}_{today}'
    chat_key  = f'chat_history_{steam_user.steam_id}'

    # 새로고침: 캐시+채팅 모두 삭제 후 redirect (로딩 화면 표시를 위해)
    if request.GET.get('refresh'):
        request.session.pop(cache_key, None)
        request.session.pop(cache_key + '_cards', None)
        request.session.pop(chat_key, None)
        request.session.modified = True
        return redirect('recommend')

    # 캐시 있으면 바로 반환
    cached = request.session.get(cache_key)
    if cached:
        if not request.session.get(chat_key):
            request.session[chat_key] = [
                {'role': 'assistant', 'content': cached},
            ]
            request.session.modified = True
        cards = request.session.get(cache_key + '_cards', [])
        return render(request, 'recommender/recommend.html', {
            'result': cached, 'cached': True, 'recommended_games': cards,
        })

    # 캐시 없음 → 로딩 화면 먼저 보여주고 JS가 /recommend/run/ 을 비동기 호출
    return render(request, 'recommender/recommend.html', {'loading': True})


def _build_deals_data(steam_user):
    """유저 분석 결과 + 점수화로 선별된 후보 딜(최대 10개) 반환.

    반환: (user_games_data, deals_data, profile)
    """
    from django.db.models import Q
    from .analyzer import analyze_user, score_deal

    owned_app_ids = set(
        steam_user.user_games.filter(source='steam')
        .exclude(game__steam_app_id=None)
        .values_list('game__steam_app_id', flat=True)
    )

    # 분석용으로는 상위 20개를 보고, LLM에는 상위 10개만 전달
    top_for_analysis = list(
        UserGame.objects
        .filter(user=steam_user)
        .select_related('game')
        .order_by('-playtime_minutes')[:20]
    )
    user_games_full = [
        {
            'name': ug.game.name,
            'playtime_minutes': ug.playtime_minutes,
            'genres': ug.game.genres or [],
            'tags': ug.game.tags or [],
        }
        for ug in top_for_analysis
    ]
    profile = analyze_user(user_games_full)
    user_games_data = user_games_full[:10]

    # 보유 장르 집합 (점수화에 사용)
    owned_genres = set()
    for g in user_games_full:
        owned_genres.update(g['genres'])

    # 후보 풀: 상위 장르 1개라도 겹치는 것 우선, 부족하면 평점순 fallback
    base_qs = (
        Deal.objects
        .filter(category='popular', platform='steam')
        .exclude(game__steam_app_id__in=owned_app_ids)
        .select_related('game')
    )
    candidates = []
    if profile and profile['top_genres']:
        genre_filter = Q()
        for g in profile['top_genres']:
            genre_filter |= Q(game__genres__contains=[g])
        candidates = list(base_qs.filter(genre_filter).order_by('-game__review_score')[:40])
    if len(candidates) < 30:
        existing = {d.id for d in candidates}
        candidates += list(
            base_qs.exclude(id__in=existing).order_by('-game__review_score')[:30 - len(candidates)]
        )

    # 후보를 dict로 변환 후 점수화
    candidate_dicts = [
        {
            'name': d.game.name,
            'sale_price': float(d.sale_price) if d.sale_price else None,
            'discount_percent': d.discount_percent,
            'genres': d.game.genres or [],
            'tags': d.game.tags or [],
            'deal_url': d.deal_url,
            'review_score': d.game.review_score,
        }
        for d in candidates
    ]
    if profile:
        candidate_dicts.sort(
            key=lambda d: score_deal(d, profile, owned_genres),
            reverse=True,
        )
    deals_data = candidate_dicts[:10]

    return user_games_data, deals_data, profile


@login_required(login_url='login')
def recommend_run(request):
    """JS에서 fetch()로 호출 — Ollama 추천 실행 후 JSON 반환."""
    steam_user = request.user.steam_profile
    today = str(date.today())
    cache_key = f'recommendation_{steam_user.steam_id}_{today}'
    chat_key  = f'chat_history_{steam_user.steam_id}'

    cached = request.session.get(cache_key)
    if cached:
        cards = request.session.get(cache_key + '_cards', [])
        return JsonResponse({'result': cached, 'cards': cards})

    user_games_data, deals_data, profile = _build_deals_data(steam_user)

    try:
        result = get_recommendation(user_games_data, deals_data, profile)
    except Exception as e:
        return JsonResponse({'error': f'추천 서버 오류: {e}'}, status=503)

    cards = _parse_recommended_games(result)
    top_game_names = ', '.join(g['name'] for g in user_games_data[:5])
    chat_system = (
        f"당신은 Steam 게임 추천 전문가입니다. "
        f"사용자는 주로 {top_game_names} 등을 즐깁니다. "
        f"아래는 당신이 방금 제공한 추천 결과입니다."
    )
    request.session[cache_key] = result
    request.session[cache_key + '_cards'] = cards
    request.session[chat_key] = [
        {'role': 'user', 'content': chat_system},
        {'role': 'assistant', 'content': result},
    ]
    request.session.modified = True

    return JsonResponse({'result': result, 'cards': cards})


@require_POST
@login_required(login_url='login')
def chat(request):
    try:
        body = json.loads(request.body)
        user_message = body.get('message', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    if not user_message:
        return JsonResponse({'error': '메시지를 입력하세요.'}, status=400)

    steam_user = request.user.steam_profile
    chat_key = f'chat_history_{steam_user.steam_id}'
    history = request.session.get(chat_key, [])

    history.append({'role': 'user', 'content': user_message})

    try:
        reply = chat_with_context(history)
    except Exception as e:
        return JsonResponse({'error': f'AI 서버 오류: {e}'}, status=503)

    history.append({'role': 'assistant', 'content': reply})

    # 앞쪽 시스템 컨텍스트(2개) 유지 + 최근 8턴(user+assistant 4쌍)만 보존
    if len(history) > 10:
        history = history[:2] + history[-8:]

    request.session[chat_key] = history
    request.session.modified = True

    return JsonResponse({'reply': reply})
