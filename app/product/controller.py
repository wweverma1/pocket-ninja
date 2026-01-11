import os
import threading
from datetime import datetime, timezone, timedelta
from flask import request, jsonify

from app.models.response import Response
from app.models.collections.user import User
from app.models.collections.store import Store
from app.models.collections.product import Product
from app.models.collections.receipt import Receipt
from app.utils.auth_helper import token_required
from app.utils.gemini_helper import get_receipt_analysis_instruction, analyze_receipt_with_gemini
from app.utils.image_helper import optimize_image_stream

TARGET_CITY = os.getenv("TARGET_CITY")


def penalize_user_for_bad_upload(user_id):
    try:
        User.penalize_user(user_id=user_id)
        print(f"Async penalty update for user {user_id} complete.")
    except Exception as e:
        print(f"Async penalty update failed for user {user_id}: {e}")


def reward_user_and_update_store(store_name, user_id, contribution_count=None, total_expenditure=None):
    if store_name:
        Store.add_store_if_not_exists(store_name)

    try:
        rank_increment = contribution_count * 5
        User.update_user_stats(
            user_id=user_id,
            rank_increment=rank_increment,
            contribution=contribution_count,
            expenditure=total_expenditure,
            savings=0.0
        )
        print(f"Async reward update for user {user_id} complete.")
    except Exception as e:
        print(f"Async reward update failed for user {user_id}: {e}")


@token_required
def add_or_update_product_details(current_user):
    """
    PUT /product/details
    """
    user_id = str(current_user['_id'])

    try:
        if not User.is_upload_allowed(user_id):
            response = Response(
                message_en="Uploads forbidden due to repeated bad uploads. Please try again in some time.",
                message_ja="不正なアップロードが繰り返されたため、アップロードは禁止されています。しばらくしてからもう一度お試しください。"
            )
            return jsonify(response.to_dict()), 403

        receipt_id = Receipt.create_receipt(user_id)

        # 1. Image Check
        if 'receiptImage' not in request.files or request.files['receiptImage'].filename == '':
            response = Response(message_en="No receipt image provided.", message_ja="領収書の画像が提供されていません。")
            if receipt_id:
                Receipt.update_receipt_status(
                    receipt_id, "FAILED", {"en": response.message_en, "ja": response.message_ja})
            return jsonify(response.to_dict()), 400

        optimized_image_bytes = optimize_image_stream(request.files['receiptImage'])
        if not optimized_image_bytes:
            response = Response(
                message_en="Image processing failed.",
                message_ja="画像処理に失敗しました。"
            )
            if receipt_id:
                Receipt.update_receipt_status(receipt_id, "FAILED", {
                    "en": response.message_en,
                    "ja": response.message_ja
                })
            return jsonify(response.to_dict()), 400

        # 2. Context Data
        available_stores = Store.get_all_store_names()
        # product_catalog = Product.get_product_catalog()

        # Calculate Date Range for Gemini Validation
        jst_tz = timezone(timedelta(hours=9))
        now_jst = datetime.now(jst_tz)
        valid_end_date = now_jst.strftime("%Y-%m-%d")
        valid_start_date = (now_jst - timedelta(days=3)).strftime("%Y-%m-%d")

        # 4. Call Gemini
        analysis_result = analyze_receipt_with_gemini(optimized_image_bytes, TARGET_CITY, valid_start_date, valid_end_date, available_stores)

        if not analysis_result:
            response = Response(message_en="Receipt Analysis failed. Please try again.",
                                message_ja="レシート分析に失敗しました。もう一度お試しください。")
            if receipt_id:
                Receipt.update_receipt_status(receipt_id, "FAILED", {
                    "en": response.message_en,
                    "ja": response.message_ja
                })
            return jsonify(response.to_dict()), 502

        # 5. Error Code Validation
        error_code = analysis_result.get("error_code")

        if error_code != 0:
            threading.Thread(target=penalize_user_for_bad_upload, args=(user_id,)).start()

            error_map = {
                1: {"en": "This image does not appear to be a receipt. Please upload a valid receipt.", "ja": "この画像は領収書ではないようです。有効な領収書をアップロードしてください。"},
                2: {"en": "This receipt appears to be edited or tampered with. Please upload an original receipt.", "ja": "この領収書は編集または改ざんされているようです。元の領収書をアップロードしてください。"},
                3: {"en": "This receipt is more than 3 days old. Please upload receipts from recent purchases.", "ja": "このレシートは3日以上前のものです。最近の購入のレシートをアップロードしてください。"},
                4: {"en": "This store type is not supported. We only accept receipts from convenience stores and supermarkets.", "ja": "この店舗タイプはサポートされていません。コンビニエンスストアまたはスーパーマーケットのレシートのみ受け付けております。"},
                5: {"en": "This store is not located in Sapporo.", "ja": "この店舗は札幌にはありません。"},
            }

            err_obj = error_map.get(error_code, {"en": "Invalid receipt.", "ja": "無効なレシートです。"})

            response = Response(
                message_en=err_obj["en"],
                message_ja=err_obj["ja"]
            )

            if receipt_id:
                Receipt.update_receipt_status(receipt_id, "FAILED", {
                    "en": response.message_en,
                    "ja": response.message_ja
                })
            return jsonify(response.to_dict()), 400

        # 6. Extract & Fallback Logic
        purchase_date_str = analysis_result.get("purchase_date")
        store_name = analysis_result.get("store_name")
        store_identifier = analysis_result.get("store_identifier")
        total_amount = analysis_result.get("total_amount") or 0.0
        products = analysis_result.get("products") or []

        if not products:
            threading.Thread(target=penalize_user_for_bad_upload, args=(user_id,)).start()

            response = Response(
                message_en="No products found in receipt.",
                message_ja="レシートに商品が見つかりませんでした。"
            )

            if receipt_id:
                Receipt.update_receipt_status(receipt_id, "FAILED", {
                    "en": response.message_en,
                    "ja": response.message_ja
                })
            return jsonify(response.to_dict()), 400

        threading.Thread(
            target=reward_user_and_update_store,
            args=(store_name, user_id, len(products), float(total_amount))
        ).start()

        try:
            purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            purchase_date = datetime.now() - timedelta(days=3)

        # 7. Update DB
        # updated_count = Product.bulk_upsert(purchase_date, store_name, products)

        response = Response(
            errorStatus=0,
            message_en="Receipt processed successfully!",
            message_ja="レシートの処理が完了しました！"
        )

        if receipt_id:
            Receipt.update_receipt_status(
                receipt_id=receipt_id,
                status="SUCCESS",
                status_message={"en": response.message_en, "ja": response.message_ja},
                purchase_date=purchase_date,
                store_name=store_name,
                store_identifier=store_identifier,
                total_amount=total_amount,
                products_found=products
            )

        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Product Update Error: {e}")
        return jsonify(Response(message_en="Internal server error.", message_ja="内部サーバーエラー。").to_dict()), 500


def get_product_details():
    response = Response(message_en="API Not implemented yet", message_ja="APIはまだ実装されていません")
    return jsonify(response.to_dict()), 501
