from flask import request, jsonify
from app.models.collections.user import User
from app.models.collections.receipt import Receipt
from app.utils.auth_helper import token_required
from app.models.response import Response


@token_required
def get_profile(current_user):
    try:
        User.check_and_reset_monthly_stats(str(current_user['_id']))

        rating_obj = current_user.get('userRating', {})
        total_score = rating_obj.get('totalScore', 5)
        raters_count = len(rating_obj.get('ratedByUsers', []))

        avg_rating = round(total_score / (raters_count + 1), 2)

        profile_data = {
            "username": current_user.get('username'),
            "userAvatarId": current_user.get('userAvatarId', 1),
            "preferredStoreProximity": current_user.get('preferredStoreProximity', 0.5),
            "joinedAt": current_user.get('joinedAt'),
            "rankScore": current_user.get('rankScore', 0),
            "lastRankIncrement": current_user.get('lastRankIncrement', 0),
            "totalContributions": current_user.get('totalContributions', 0),
            "totalExpenditure": current_user.get('totalExpenditure', 0.0),
            "estimatedTotalSavings": current_user.get('estimatedTotalSavings', 0.0),
            "userRating": avg_rating,
            "monthlyStats": {
                "month": current_user.get('statsMonth'),
                "contributions": current_user.get('monthlyContributions', 0),
                "expenditure": current_user.get('monthlyExpenditure', 0.0),
                "savings": current_user.get('monthlySavings', 0.0)
            }
        }

        response = Response(
            errorStatus=0,
            message_en="User profile retrieved successfully.",
            message_ja="ユーザー プロファイルが正常に取得されました。",
            result=profile_data
        )
        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Profile Retrieval Error: {e}")
        response = Response(
            message_en="Failed to retrieve user profile.",
            message_ja="ユーザー プロファイルの取得に失敗しました。"
        )
        return jsonify(response.to_dict()), 500


@token_required
def update_username(current_user):
    try:
        data = request.get_json()
        if not data or 'username' not in data:
            response = Response(
                message_en="No input data provided.",
                message_ja="入力データがありません。"
            )
            return jsonify(response.to_dict()), 400

        chosen_username = data.get('username', '').strip()

        if len(chosen_username) < 3:
            response = Response(
                message_en="username must be at least 3 characters long.",
                message_ja="username は 3 文字以上である必要があります。"
            )
            return jsonify(response.to_dict()), 400

        user_id = str(current_user['_id'])
        status = User.update_username(user_id, chosen_username)

        if status == 0:
            result = {"username": chosen_username}
            response = Response(
                errorStatus=0,
                message_en="Username updated successfully!",
                message_ja="ユーザー名が正常に更新されました。",
                result=result
            )
            return jsonify(response.to_dict()), 200

        elif status == 1:
            response = Response(
                message_en="This username is already taken. Please try another.",
                message_ja="このユーザー名は既に使用されています。別の名前を試してください。"
            )
            return jsonify(response.to_dict()), 409

        elif status == 3:
            response = Response(
                message_en="Username cannot exceed 20 characters.",
                message_ja="ユーザー名は20文字以内で入力してください。"
            )
            return jsonify(response.to_dict()), 400

        else:
            response = Response(
                message_en="Internal database error. Please try again later.",
                message_ja="データベースエラーが発生しました。後でもう一度お試しください。"
            )
            return jsonify(response.to_dict()), 500

    except Exception as e:
        print(f"Onboarding Error: {e}")
        response = Response(
            message_en="Internal server error.",
            message_ja="内部サーバーエラー。"
        )
        return jsonify(response.to_dict()), 500


@token_required
def update_avatar_id(current_user):
    try:
        data = request.get_json()
        if not data or 'userAvatarId' not in data:
            response = Response(
                message_en="No input data provided.",
                message_ja="入力データがありません。"
            )
            return jsonify(response.to_dict()), 400

        avatar_id = data.get('userAvatarId')

        if not isinstance(avatar_id, int) or not (1 <= avatar_id <= 8):
            response = Response(
                message_en="userAvatarId must be an integer between 1 and 8.",
                message_ja="userAvatarId は 1 ～ 8 の整数である必要があります。"
            )
            return jsonify(response.to_dict()), 400

        User.update_avatar_id(str(current_user['_id']), avatar_id)

        response = Response(
            errorStatus=0,
            message_en="User avatar updated successfully!",
            message_ja="ユーザーアバターが正常に更新されました。",
            result={"userAvatar": avatar_id}
        )
        return jsonify(response.to_dict()), 200
    except Exception as e:
        print(f"Error updating user avatar: {e}")
        return jsonify(Response(message_en="Internal server error.", message_ja="内部サーバーエラー。").to_dict()), 500


@token_required
def update_proximity(current_user):
    try:
        data = request.get_json()
        if not data or 'preferredStoreProximity' not in data:
            response = Response(
                message_en="No input data provided.",
                message_ja="入力データがありません。"
            )
            return jsonify(response.to_dict()), 400

        proximity = data.get('preferredStoreProximity')

        if not isinstance(proximity, (int, float)) or proximity <= 0:
            response = Response(
                message_en="preferredStoreProximity must be a positive number.",
                message_ja="preferredStoreProximity は正の数値である必要があります。"
            )
            return jsonify(response.to_dict()), 400

        if proximity > 5:
            proximity = 5

        User.update_proximity(str(current_user['_id']), float(proximity))

        response = Response(
            errorStatus=0,
            message_en="Preferred store proximity updated successfully!",
            message_ja="優先店舗の近接性が正常に更新されました。",
            result={"preferredStoreProximity": float(proximity)}
        )
        return jsonify(response.to_dict()), 200
    except Exception as e:
        print(f"Error updating proximity: {e}")
        return jsonify(Response(message_en="Internal server error.", message_ja="内部サーバーエラー。").to_dict()), 500


@token_required
def get_submitted_receipts(current_user):
    try:
        user_id = str(current_user['_id'])
        month = request.args.get('month')

        receipts = Receipt.get_by_user(user_id, month=month)

        response = Response(
            errorStatus=0,
            message_en="Receipts fetched successfully.",
            message_ja="領収書の取得に成功しました。",
            result=receipts
        )
        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Error fetching receipts: {e}")
        return jsonify(Response(message_en="Internal server error.", message_ja="内部サーバーエラー。").to_dict()), 500
