import re
import json
from datetime import date
from django.shortcuts import render
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

    if request.GET.get('refresh'):
        request.session.pop(cache_key, None)
        request.session.pop(cache_key + '_cards', None)

    cached = request.session.get(cache_key)
    chat_key = f'chat_history_{steam_user.steam_id}'
    if cached:
        # 채팅 히스토리가 없으면 추천 결과로 초기화
        if not request.session.get(chat_key):
            request.session[chat_key] = [
                {'role': 'assistant', 'content': cached},
            ]
            request.session.modified = True
        cards = request.session.get(cache_key + '_cards', [])
        return render(request, 'recommender/recommend.html', {
            'result': cached, 'cached': True, 'recommended_games': cards,
        })

    owned_app_ids = set(
        steam_user.user_games.filter(source='steam')
        .exclude(game__steam_app_id=None)
        .values_list('game__steam_app_id', flat=True)
    )

    top_games = (
        UserGame.objects
        .filter(user=steam_user)
        .select_related('game')
        .order_by('-playtime_minutes')[:10]
    )
    user_games_data = [
        {
            'name': ug.game.name,
            'playtime_minutes': ug.playtime_minutes,
            'genres': ug.game.genres,
        }
        for ug in top_games
    ]

    # 인기 게임(popular) 중 미보유 게임을 평점 순으로 최대 40개
    deals = (
        Deal.objects
        .filter(category='popular', platform='steam')
        .exclude(game__steam_app_id__in=owned_app_ids)
        .select_related('game')
        .order_by('-game__review_score')[:40]
    )
    deals_data = [
        {
            'name': d.game.name,
            'sale_price': d.sale_price,
            'discount_percent': d.discount_percent,
            'genres': d.game.genres,
            'deal_url': d.deal_url,
            'review_score': d.game.review_score,
        }
        for d in deals
    ]

    try:
        result = get_recommendation(user_games_data, deals_data)
    except Exception as e:
        return render(request, 'recommender/recommend.html', {'error': f'추천 서버 오류: {e}'})

    cards = _parse_recommended_games(result)
    request.session[cache_key] = result
    request.session[cache_key + '_cards'] = cards

    # 채팅 히스토리 초기화: 추천 결과를 첫 번째 assistant 메시지로 설정
    chat_key = f'chat_history_{steam_user.steam_id}'
    system_context = _build_system_context(user_games_data, deals_data)
    request.session[chat_key] = [
        {'role': 'user', 'content': system_context},
        {'role': 'assistant', 'content': result},
    ]
    request.session.modified = True

    return render(request, 'recommender/recommend.html', {
        'result': result, 'cached': False, 'recommended_games': cards,
    })


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

    # 히스토리가 너무 길어지지 않도록 앞쪽 시스템 컨텍스트(2개)는 유지하고 최근 20턴만 보존
    if len(history) > 22:
        history = history[:2] + history[-20:]

    request.session[chat_key] = history
    request.session.modified = True

    return JsonResponse({'reply': reply})
