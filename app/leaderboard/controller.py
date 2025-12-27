from flask import jsonify
from app.models.collections.user import User
from app.utils.auth_helper import token_optional
from app.models.response import Response


@token_optional
def get_leaderboard(current_user):
    """
    GET /leaderboard/
    Returns the top 3 users based on monthly contributions.
    If authenticated, also returns the current user's rank.
    """
    try:
        # 1. Get Top 3 Users (Filtered by monthlyContributions > 0)
        top_users = User.get_top_users(limit=3)

        result_data = {
            "leaderboard": top_users
        }

        # 2. If User is Logged In, fetch their personal rank and calculate milestone
        if current_user:
            user_id = str(current_user['_id'])
            # Score detail now returns monthlyContributions as 'score'
            user_score_detail = User.get_user_score_detail(user_id)

            if user_score_detail:
                my_rank = user_score_detail['rank']
                my_score = user_score_detail['score']

                result_data["userStats"] = {
                    "rank": my_rank
                }

                milestone_en = ""
                milestone_ja = ""

                # Ensure we have users in the leaderboard to compare against
                if not top_users:
                    # Edge case: No users with >0 contributions yet
                    milestone_en = "Be the first to contribute!"
                    milestone_ja = "最初の貢献者になりましょう！"

                elif my_rank == 1:
                    milestone_en = "Thank you for being our top contributor!"
                    milestone_ja = "トップコントリビューターとしてのご協力ありがとうございます！"

                elif my_rank == 2:
                    # Compare with Rank 1
                    target_score = top_users[0]['score']
                    diff = target_score - my_score
                    # Handle Tie Breaker: If scores match but you are rank 2,
                    # you lost on 'joinedAt', so you need +1 point to win.
                    if diff <= 0:
                        diff = 1

                    milestone_en = f"You need {diff} points to reach 1st place!"
                    milestone_ja = f"1位になるにはあと {diff} ポイント必要です！"

                elif my_rank == 3:
                    # Compare with Rank 2
                    if len(top_users) >= 2:
                        target_score = top_users[1]['score']
                        diff = target_score - my_score
                        if diff <= 0:
                            diff = 1

                        milestone_en = f"You need {diff} points to reach 2nd place!"
                        milestone_ja = f"2位になるにはあと {diff} ポイント必要です！"
                    else:
                        milestone_en = "Keep contributing to rise up!"
                        milestone_ja = "貢献してランクを上げましょう！"

                else:
                    # Rank > 3 (4th, 5th, etc.)
                    # Compare with Rank 3
                    if len(top_users) >= 3:
                        target_score = top_users[2]['score']
                        diff = target_score - my_score
                        if diff <= 0:
                            diff = 1

                        milestone_en = f"You need {diff} points to be one of our top contributors."
                        milestone_ja = f"トップコントリビューターになるには、あと {diff} ポイント必要です。"
                    else:
                        # Aiming for the last visible spot
                        target_score = top_users[-1]['score']
                        diff = target_score - my_score
                        if diff <= 0:
                            diff = 1

                        milestone_en = f"You need {diff} points to join the leaderboard."
                        milestone_ja = f"リーダーボードに参加するには、あと {diff} ポイント必要です。"

                result_data["userStats"]["nextMilestone"] = {
                    "en": milestone_en,
                    "ja": milestone_ja
                }
            else:
                # User exists but has 0 contributions, so get_user_score_detail returned None
                result_data["userStats"] = {
                    "rank": None,
                    "nextMilestone": {
                        "en": "Make a contribution to get ranked!",
                        "ja": "貢献してランクインしましょう！"
                    }
                }

        response = Response(
            errorStatus=0,
            message_en="Leaderboard fetched successfully.",
            message_ja="リーダーボードが正常に取得されました。",
            result=result_data
        )
        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Error fetching leaderboard: {e}")
        return jsonify(Response(message_en="Internal server error.", message_ja="内部サーバーエラー。").to_dict()), 500
