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

# --- Async Task for User Stats ---

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
        # Simple gamification: 5 points per product contributed
        rank_increment = contribution_count * 5

        User.update_user_stats(
            user_id=user_id,
            rank_increment=rank_increment,
            contribution=contribution_count,
            expenditure=total_expenditure,
            savings=0.0  # Savings are calculated in the Comparison flow, not Contribution flow
        )
        print(f"Async reward update for user {user_id} complete.")
    except Exception as e:
        print(f"Async reward update failed for user {user_id}: {e}")


@token_required
def add_or_update_product_details(current_user):
    """
    PUT /product/details
    Updated to handle multipart/form-data for faster uploads.
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

        # 1. Check if the file is present in the request
        if 'receiptImage' not in request.files:
            response = Response(
                message_en="No receipt image provided.",
                message_ja="領収書の画像が提供されていません。"
            )
            if receipt_id:
                Receipt.update_receipt_status(receipt_id, "FAILED", {
                    "en": response.message_en,
                    "ja": response.message_ja
                })
            return jsonify(response.to_dict()), 400

        file_storage = request.files['receiptImage']

        # 2. Validation: Ensure filename exists and is not empty
        if file_storage.filename == '':
            # Handle empty selection
            return jsonify({"message": "No file selected"}), 400

        # 3. Optimization: Pass the file directly (No Base64 decoding needed yet)
        # We pass the file to our helper function
        optimized_image_bytes = optimize_image_stream(file_storage)

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

        # 1. Get Context Data
        available_stores = Store.get_all_store_names()
        available_products = Product.get_all_product_names()
        jst_tz = timezone(timedelta(hours=9))
        current_date_jp_str = datetime.now(jst_tz).strftime("%Y-%m-%d")

        # 2. Prepare Gemini Instruction
        instruction = get_receipt_analysis_instruction(
            date_str=current_date_jp_str,
            target_city=TARGET_CITY,
            available_stores=available_stores,
            product_names=available_products
        )

        # 3. Call Gemini
        analysis_result = analyze_receipt_with_gemini(optimized_image_bytes, instruction)

        if not analysis_result:
            response = Response(message_en="AI Analysis failed. Please try again.",
                                message_ja="AI分析に失敗しました。もう一度お試しください。")
            if receipt_id:
                Receipt.update_receipt_status(receipt_id, "FAILED", {
                    "en": response.message_en,
                    "ja": response.message_ja
                })
            return jsonify(response.to_dict()), 502

        # 4. Check Gemini Error Codes
        error_code = analysis_result.get("error_code")

        if error_code != 0:
            # Penalize user for bad receipt
            thread = threading.Thread(
                target=penalize_user_for_bad_upload,
                args=(user_id,)
            )
            thread.start()

            error_map = {
                1: {"en": "Receipt is not from a supported store.", "ja": "レシートはサポートされているストアのものではありません。"},
                2: {"en": "Receipt appears edited.", "ja": "レシートが編集されている可能性があります。"},
                3: {"en": "Receipt date is too old or invalid.", "ja": "レシートの日付が古すぎるか、無効です。"},
                4: {"en": "Could not read the date on the receipt.", "ja": "レシートの日付を読み取れませんでした。"},
                5: {"en": "Store is not located in Sapporo.", "ja": "店舗が札幌市外のようです。"},
                6: {"en": "Could not read store location on the receipt.", "ja": "店舗の場所を特定できませんでした。"},
                7: {"en": "Could not read store name on the receipt.", "ja": "店舗名を特定できませんでした。"},
            }

            err_obj = error_map.get(error_code, {"en": "Unknown validation error.", "ja": "不明なエラーが発生しました。"})

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

        # 5. Extract Valid Data
        purchase_date_str = analysis_result.get("purchase_date", None)
        store_name = analysis_result.get("store_name", None)
        store_identifier = analysis_result.get("store_identifier", None)
        total_amount = analysis_result.get("total_amount", 0.0)
        products = analysis_result.get("products", [])

        if not products:
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

        try:
            purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            # Fallback
            purchase_date = datetime.now() - timedelta(days=3)

        # 6. Update Product Database
        updated_count = Product.bulk_upsert(purchase_date, store_name, products)

        # 7. Async Update User Stats
        thread = threading.Thread(
            target=reward_user_and_update_store,
            args=(store_name, user_id, updated_count, float(total_amount))
        )
        thread.start()

        response = Response(
            errorStatus=0,
            message_en="Receipt processed successfully!",
            message_ja="レシートの処理が完了しました！",
        )

        if receipt_id:
            Receipt.update_receipt_status(
                receipt_id=receipt_id,
                status="SUCCESS",
                status_message={
                    "en": response.message_en,
                    "ja": response.message_ja
                },
                purchase_date=purchase_date,
                store_name=store_name,
                store_identifier=store_identifier,
                total_amount=total_amount,
                products_found=products,
                products_updated=updated_count
            )

        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Product Update Error: {e}")

        response = Response(
            message_en="Internal server error.",
            message_ja="内部サーバーエラー。"
        )

        return jsonify(response.to_dict()), 500


def get_product_details():
    response = Response(message_en="API Not implemented yet", message_ja="APIはまだ実装されていません")
    return jsonify(response.to_dict()), 501
