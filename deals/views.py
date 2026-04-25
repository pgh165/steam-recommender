import threading
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from library.models import Game
from .models import Deal
from .price_compare import get_price_comparison

FETCH_COOLDOWN_MINUTES = 60  # 마지막 수집 후 이 시간이 지나야 재수집


def _collect_genres(deals_qs):
    counts = {}
    for d in deals_qs:
        for g in (d.game.genres or []):
            counts[g] = counts.get(g, 0) + 1
    return sorted(counts, key=lambda g: -counts[g])


def _run_fetch_in_background():
    """별도 스레드에서 fetch_deals 실행 (Django DB 연결은 스레드마다 독립)."""
    try:
        from deals.crawler import fetch_steam_deals, fetch_directgames_deals
        fetch_steam_deals()
        fetch_directgames_deals()
    except Exception:
        pass


@login_required(login_url='login')
def deals_list(request):
    platform = request.GET.get('platform', '')
    genre    = request.GET.get('genre', '')
    steam_user = request.user.steam_profile

    # 새로고침 요청: 마지막 수집이 FETCH_COOLDOWN_MINUTES 이상 지났으면 백그라운드 수집
    if request.GET.get('refresh'):
        last = Deal.objects.order_by('-fetched_at').values_list('fetched_at', flat=True).first()
        cooldown_passed = (
            last is None or
            timezone.now() - last > timedelta(minutes=FETCH_COOLDOWN_MINUTES)
        )
        if cooldown_passed:
            t = threading.Thread(target=_run_fetch_in_background, daemon=True)
            t.start()
        # 새로고침 파라미터 제거 후 리다이렉트 (새로고침 중복 방지)
        params = []
        if platform:
            params.append(f'platform={platform}')
        if genre:
            params.append(f'genre={genre}')
        params.append('fetching=1')
        return redirect(f"{request.path}?{'&'.join(params)}")

    fetching = bool(request.GET.get('fetching'))

    owned_app_ids = set(
        steam_user.user_games.filter(source='steam')
        .exclude(game__steam_app_id=None)
        .values_list('game__steam_app_id', flat=True)
    )
    owned_names = set(
        steam_user.user_games.values_list('game__name', flat=True)
    )

    base_qs = (
        Deal.objects
        .exclude(game__steam_app_id__in=owned_app_ids)
        .exclude(game__name__in=owned_names)
        .select_related('game')
    )
    if platform:
        base_qs = base_qs.filter(platform=platform)

    popular_all = base_qs.filter(category__in=('popular', 'top_sellers'))
    all_genres  = _collect_genres(popular_all)

    popular_filtered = popular_all.filter(game__genres__contains=[genre]) if genre else popular_all
    specials_qs = base_qs.filter(category='specials')
    if genre:
        specials_qs = specials_qs.filter(game__genres__contains=[genre])

    popular_deals  = list(popular_filtered.order_by('-game__review_score'))
    specials_deals = list(specials_qs.order_by('-discount_percent'))

    def fix_thumbnails(items):
        for d in items:
            if d.game.steam_app_id and 'media.steampowered.com' in (d.game.thumbnail_url or ''):
                d.game.thumbnail_url = (
                    f'https://cdn.akamai.steamstatic.com/steam/apps/{d.game.steam_app_id}/header.jpg'
                )
        return items

    sections = []
    if popular_deals:
        sections.append(('인기 게임', fix_thumbnails(popular_deals)))
    if specials_deals:
        sections.append(('할인 특가', fix_thumbnails(specials_deals)))

    last_updated = Deal.objects.order_by('-fetched_at').values_list('fetched_at', flat=True).first()
    return render(request, 'deals/deals.html', {
        'sections':     sections,
        'platform':     platform,
        'genre':        genre,
        'all_genres':   all_genres,
        'last_updated': last_updated,
        'fetching':     fetching,
        'cooldown_minutes': FETCH_COOLDOWN_MINUTES,
    })


@login_required(login_url='login')
def game_detail(request, app_id):
    game = get_object_or_404(Game, steam_app_id=app_id)
    steam_deal = Deal.objects.filter(game=game, platform='steam').first()
    dg_deal    = Deal.objects.filter(game=game, platform='directgames').first()
    youtube_query = game.name.replace(' ', '+') + '+게임+트레일러'

    steam_is_best = False
    dg_is_best    = False
    if steam_deal and dg_deal and steam_deal.sale_price and dg_deal.sale_price:
        steam_is_best = steam_deal.sale_price <= dg_deal.sale_price
        dg_is_best    = not steam_is_best
    elif steam_deal and not dg_deal:
        steam_is_best = True
    elif dg_deal and not steam_deal:
        dg_is_best = True

    return render(request, 'deals/game_detail.html', {
        'game':          game,
        'steam_deal':    steam_deal,
        'dg_deal':       dg_deal,
        'steam_is_best': steam_is_best,
        'dg_is_best':    dg_is_best,
        'youtube_query': youtube_query,
    })


@login_required(login_url='login')
def price_compare(request):
    comparisons = get_price_comparison()
    return render(request, 'deals/price_compare.html', {'comparisons': comparisons})


@login_required(login_url='login')
def search_games(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return render(request, 'deals/search.html', {'query': query, 'results': [], 'total': 0})

    games_qs = Game.objects.filter(
        Q(name__icontains=query) | Q(korean_name__icontains=query)
    ).prefetch_related('deals').order_by('-review_score')[:50]

    results = []
    for game in games_qs:
        steam_deal = next((d for d in game.deals.all() if d.platform == 'steam'), None)
        dg_deal    = next((d for d in game.deals.all() if d.platform == 'directgames'), None)
        best_deal  = steam_deal or dg_deal
        if game.steam_app_id and 'media.steampowered.com' in (game.thumbnail_url or ''):
            game.thumbnail_url = (
                f'https://cdn.akamai.steamstatic.com/steam/apps/{game.steam_app_id}/header.jpg'
            )
        results.append({
            'game': game,
            'steam_deal': steam_deal,
            'dg_deal': dg_deal,
            'best_deal': best_deal,
        })

    return render(request, 'deals/search.html', {
        'query': query,
        'results': results,
        'total': len(results),
    })
