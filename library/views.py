import time
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Game, UserGame
from .steam_api import get_owned_games, get_app_details


@login_required(login_url='login')
def library(request):
    steam_user = request.user.steam_profile
    steam_games = list(steam_user.user_games.filter(source='steam').select_related('game').order_by('-playtime_minutes'))

    genre_map = {}
    for ug in steam_games:
        genres = ug.game.genres if ug.game.genres else []
        primary = genres[0] if genres else '기타'
        genre_map.setdefault(primary, []).append(ug)
    steam_by_genre = sorted(genre_map.items(), key=lambda x: -len(x[1]))

    return render(request, 'library/library.html', {
        'steam_user': steam_user,
        'user_games': steam_games,
        'steam_by_genre': steam_by_genre,
    })


@login_required(login_url='login')
def sync_library(request):
    if request.method != 'POST':
        return redirect('library')

    steam_user = request.user.steam_profile
    games = get_owned_games(steam_user.steam_id)

    if not games:
        steam_games = steam_user.user_games.filter(source='steam').select_related('game').order_by('-playtime_minutes')
        return render(request, 'library/library.html', {
            'steam_user': steam_user,
            'error': '게임 목록을 불러올 수 없습니다. Steam 프로필을 공개로 설정해주세요.',
            'user_games': steam_games,
        })

    for item in games:
        app_id = item['appid']
        thumbnail = f'https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg'
        game, _ = Game.objects.update_or_create(
            steam_app_id=app_id,
            defaults={'name': item.get('name', ''), 'thumbnail_url': thumbnail},
        )
        UserGame.objects.update_or_create(
            user=steam_user,
            game=game,
            defaults={'playtime_minutes': item.get('playtime_forever', 0), 'source': 'steam'},
        )

    top_games = steam_user.user_games.filter(source='steam').select_related('game').order_by('-playtime_minutes')[:50]
    for ug in top_games:
        if not ug.game.genres:
            details = get_app_details(ug.game.steam_app_id)
            if details:
                ug.game.genres = [g['description'] for g in details.get('genres', [])]
                ug.game.tags = list(details.get('categories', []))
                ug.game.save(update_fields=['genres', 'tags'])
            time.sleep(0.5)

    steam_user.profile_updated_at = timezone.now()
    steam_user.save(update_fields=['profile_updated_at'])

    return redirect('library')
