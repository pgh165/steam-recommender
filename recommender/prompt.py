def build_prompt(user_games, deals):
    user_games_text = '\n'.join(
        f'- {g["name"]} ({g["playtime_minutes"] // 60}h) 장르: {", ".join(g["genres"]) if g.get("genres") else "미상"}'
        for g in user_games
    )

    lines = []
    for d in deals:
        score = round((d.get('review_score') or 0) * 100)
        price = d.get('sale_price')
        disc  = d.get('discount_percent', 0)
        genres = ', '.join(d.get('genres') or []) or '미상'
        price_str = f'₩{int(price):,}' if price else '가격미정'
        disc_str  = f'(-{disc}%)' if disc else ''
        lines.append(f'- {d["name"]} | {price_str}{disc_str} | {score}% | {genres}')
    deals_text = '\n'.join(lines)

    return f"""Steam 게임 추천 전문가로서 사용자 플레이 기록을 분석해 후보 목록에서 3개를 추천하세요.

[플레이 기록]
{user_games_text}

[후보 게임]
{deals_text}

답변 형식:
**취향 분석**: 2문장으로 요약

**추천 게임**
[게임명] | 가격 | 평점
추천 이유: 2문장

(3개 반복)

규칙: 후보 목록의 게임만 추천, 게임명은 반드시 [대괄호], 한국어로 답변"""
