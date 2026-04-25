def build_prompt(user_games, deals):
    user_games_text = '\n'.join(
        f'- {g["name"]} (플레이타임: {g["playtime_minutes"] // 60}시간, 장르: {", ".join(g.get("genres", []))})'
        for g in user_games
    )

    lines = []
    for d in deals:
        disc = d["discount_percent"]
        score = round(d.get("review_score", 0) * 100)
        price = d["sale_price"]
        genres = ", ".join(d.get("genres", []))
        disc_str = f' ({disc}% 할인)' if disc else ''
        lines.append(f'- {d["name"]} | 가격: {price}원{disc_str} | 평점: {score}% | 장르: {genres}')
    deals_text = '\n'.join(lines)

    return f"""당신은 게임 추천 전문가입니다. 사용자의 플레이 기록을 분석해서 Steam 인기 게임 중 가장 잘 맞는 게임을 추천해주세요.

[사용자 플레이 기록]
{user_games_text}

[Steam 인기 게임 후보 (판매량 + 평점 기준)]
{deals_text}

위 정보를 바탕으로:
1. 사용자가 좋아하는 장르/스타일을 분석해주세요.
2. 후보 게임 중 사용자에게 잘 맞는 게임 3개를 추천하고, 각각 왜 이 사람에게 맞는지 설명해주세요.
3. 추천할 때 게임명은 반드시 대괄호로 감싸서 표기하세요. 예: [Stardew Valley]
4. 추천 형식: [게임명] | 가격 | 추천 이유 (2줄 이내)

한국어로 답변해주세요."""

