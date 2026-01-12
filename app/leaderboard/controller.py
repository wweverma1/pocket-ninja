from flask import jsonify
from app.models.collections.user import User
from app.utils.auth_helper import token_optional
from app.models.response import Response


def calculate_milestone(my_rank, my_score, top_users):
    if not top_users:
        return (
            "Be the first to contribute!",
            "最初の貢献者になりましょう！"
        )

    if my_rank == 1:
        return (
            "Thank you for being our top contributor!",
            "トップコントリビューターとしてのご協力ありがとうございます！"
        )

    if my_rank == 2:
        target_score = top_users[0]['score']
        diff = max(target_score - my_score, 1)
        return (
            f"You need {diff} points to reach 1st place!",
            f"1位になるにはあと {diff} ポイント必要です！"
        )

    if my_rank == 3:
        if len(top_users) >= 2:
            target_score = top_users[1]['score']
            diff = max(target_score - my_score, 1)
            return (
                f"You need {diff} points to reach 2nd place!",
                f"2位になるにはあと {diff} ポイント必要です！"
            )
        return (
            "Keep contributing to rise up!",
            "貢献してランクを上げましょう！"
        )

    return calculate_outsider_milestone(my_score, top_users)


def calculate_outsider_milestone(my_score, top_users):
    if len(top_users) >= 3:
        target_score = top_users[2]['score']
        diff = max(target_score - my_score, 1)
        return (
            f"You need {diff} points to be one of our top contributors.",
            f"トップコントリビューターになるには、あと {diff} ポイント必要です。"
        )

    target_score = top_users[-1]['score']
    diff = max(target_score - my_score, 1)
    return (
        f"You need {diff} points to join the leaderboard.",
        f"リーダーボードに参加するには、あと {diff} ポイント必要です。"
    )


def build_user_stats(current_user, top_users):
    user_id = str(current_user['_id'])
    user_score_detail = User.get_user_score_detail(user_id)

    if not user_score_detail:
        return {
            "rank": None,
            "nextMilestone": {
                "en": "Make a contribution to get ranked!",
                "ja": "貢献してランクインしましょう！"
            }
        }

    my_rank = user_score_detail['rank']
    my_score = user_score_detail['score']

    milestone_en, milestone_ja = calculate_milestone(
        my_rank, my_score, top_users
    )

    return {
        "rank": my_rank,
        "nextMilestone": {
            "en": milestone_en,
            "ja": milestone_ja
        }
    }


@token_optional
def get_leaderboard(current_user):
    try:
        top_users = User.get_top_users(limit=3)

        result_data = {"leaderboard": top_users}

        if current_user:
            result_data["userStats"] = build_user_stats(
                current_user, top_users
            )

        response = Response(
            errorStatus=0,
            message_en="Leaderboard fetched successfully.",
            message_ja="リーダーボードが正常に取得されました。",
            result=result_data
        )
        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Error fetching leaderboard: {e}")
        return jsonify(
            Response(
                message_en="Internal server error.",
                message_ja="内部サーバーエラー。"
            ).to_dict()
        ), 500
