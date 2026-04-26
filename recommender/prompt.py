def _format_play_modes(tags):
    """tags에서 멀티/싱글/협동 정보만 짧게 추출."""
    if not tags:
        return ''
    descs = [t.get('description', '') if isinstance(t, dict) else str(t) for t in tags]
    modes = []
    if any('멀티플레이' in d or 'Multi-player' in d for d in descs):
        modes.append('멀티')
    if any('협동' in d or 'Co-op' in d for d in descs):
        modes.append('협동')
    if any('싱글 플레이' in d or 'Single-player' in d for d in descs):
        modes.append('싱글')
    return '/'.join(modes)


def build_prompt(user_games, deals, profile=None):
    user_lines = []
    for g in user_games:
        hours = g['playtime_minutes'] // 60
        genres = ', '.join((g.get('genres') or [])[:2]) or '?'
        modes = _format_play_modes(g.get('tags'))
        mode_str = f' [{modes}]' if modes else ''
        user_lines.append(f'- {g["name"]} ({hours}h, {genres}{mode_str})')
    user_games_text = '\n'.join(user_lines)

    deal_lines = []
    for d in deals:
        score = round((d.get('review_score') or 0) * 100)
        price = d.get('sale_price')
        disc  = d.get('discount_percent', 0)
        genres = ', '.join((d.get('genres') or [])[:2]) or '?'
        modes = _format_play_modes(d.get('tags'))
        mode_str = f' [{modes}]' if modes else ''
        price_str = f'₩{int(price):,}' if price else '?'
        deal_lines.append(f'- {d["name"]} | {price_str} -{disc}% | {score}% | {genres}{mode_str}')
    deals_text = '\n'.join(deal_lines)

    # 사전 분석 요약 (Python이 계산한 객관 데이터)
    analysis_block = ''
    if profile:
        analysis_block = f"\n[사전 분석]\n{profile['summary_text']}\n"

    return f"""당신은 Steam 게임 추천 전문가입니다. 아래 사전 분석과 플레이 기록을 바탕으로, 후보 게임 중 사용자에게 가장 잘 맞는 3개를 추천하세요.
{analysis_block}
[플레이 기록 상위 10개]
{user_games_text}

[추천 후보 (점수순 정렬)]
{deals_text}

답변 형식:
**취향 분석**
사용자의 플레이 패턴을 3~4문장으로 깊이 있게 분석하세요. 사전 분석 결과를 참고하되, 구체적인 게임 예시와 함께 왜 그런 취향인지 추론하세요.

**추천 게임**

[게임명] | 가격
이유: 사용자의 어떤 보유 게임과 어떻게 연결되는지 2~3문장으로 설명. 단순 장르 일치가 아니라 플레이 경험의 유사성·차별점을 짚을 것.

(위 형식으로 3개 반복)

규칙: 후보 목록의 게임만 추천. 게임명은 후보에 적힌 원문 그대로 [대괄호] 안에 (번역 금지). 한국어로 답변."""
