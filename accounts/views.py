import re
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, logout
from .models import SteamUser


def login_view(request):
    if request.method == 'POST':
        raw = request.POST.get('steam_id', '').strip()
        steam_id = _parse_steam_id(raw)
        if not steam_id:
            return render(request, 'accounts/login.html', {'error': '유효한 Steam ID 또는 프로필 URL을 입력해주세요.'})

        profile = _fetch_steam_profile(steam_id)
        if profile is None:
            return render(request, 'accounts/login.html', {'error': 'Steam 프로필을 불러올 수 없습니다. API 키를 확인해주세요.'})

        user, _ = User.objects.get_or_create(username=f'steam_{steam_id}')
        steam_user, _ = SteamUser.objects.get_or_create(user=user, defaults={'steam_id': steam_id})
        steam_user.steam_id = steam_id
        steam_user.display_name = profile.get('personaname', steam_id)
        steam_user.avatar_url = profile.get('avatarfull', '')
        steam_user.save()

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('library')

    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def _parse_steam_id(raw):
    if raw.isdigit() and len(raw) == 17:
        return raw
    match = re.search(r'steamcommunity\.com/profiles/(\d{17})', raw)
    if match:
        return match.group(1)
    match = re.search(r'steamcommunity\.com/id/(\w+)', raw)
    if match:
        return _resolve_vanity_url(match.group(1))
    return None


def _resolve_vanity_url(vanity):
    from django.conf import settings
    url = 'https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/'
    resp = requests.get(url, params={'key': settings.STEAM_API_KEY, 'vanityurl': vanity}, timeout=5)
    data = resp.json().get('response', {})
    if data.get('success') == 1:
        return data.get('steamid')
    return None


def _fetch_steam_profile(steam_id):
    from django.conf import settings
    url = 'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/'
    resp = requests.get(url, params={'key': settings.STEAM_API_KEY, 'steamids': steam_id}, timeout=5)
    players = resp.json().get('response', {}).get('players', [])
    return players[0] if players else None
