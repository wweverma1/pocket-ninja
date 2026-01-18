from flask import jsonify
from app.models.collections.user import User
from app.utils.auth_helper import token_optional
from app.models.response import Response


def calculate_milestone(my_rank, my_points, top_users):
    if not top_users:
        return (
            "Be the first to contribute!",
            "最初の貢献者になろう！"
        )

    if my_rank == 1:
        return (
            "Thank you for being our top contributor!",
            "トップコントリビューターになっていただきありがとうございます!"
        )

    if my_rank == 2:
        target_points = top_users[0]['points']
        diff = max(target_points - my_points, 5)
        return (
            f"Just {diff} more points to take 1st position!",
            f"あと {diff} ポイントで1位になれます！"
        )

    if my_rank == 3:
        if len(top_users) >= 2:
            target_points = top_users[1]['points']
            diff = max(target_points - my_points, 5)
            return (
                f"Just {diff} more points to reach 2nd position!",
                f"あと {diff} ポイントで2位になれます！"
            )
        return (
            "You're in the top 3! Keep it up!",
            "トップ3入り！その調子！"
        )

    return calculate_outsider_milestone(my_points, top_users)


def calculate_outsider_milestone(my_points, top_users):
    if len(top_users) >= 3:
        target_points = top_users[2]['points']
        diff = max(target_points - my_points, 5)
        return (
            f"So close! Just {diff} more points to reach top 3!"
            f"あと {diff} ポイントでトップ3入り！"
        )

    target_points = top_users[-1]['points']
    diff = max(target_points - my_points, 5)
    return (
        f"Only {diff} more points to join the leaderboard!",
        f"あと {diff} ポイントでランクイン！"
    )


def build_user_stats(current_user, top_users):
    user_score_detail = User.get_user_score_detail(current_user)

    if not user_score_detail:
        return {
            "rank": None,
            "nextMilestone": {
                "en": "Make a contribution to get ranked!",
                "ja": "貢献してランクインしましょう！"
            }
        }

    my_rank = user_score_detail['rank']
    my_points = user_score_detail['points']

    milestone_en, milestone_ja = calculate_milestone(
        my_rank, my_points, top_users
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