import os
import threading
from datetime import datetime, timedelta
from flask import request, jsonify


from app.models.response import Response
from app.models.collections.user import User
from app.models.collections.store import Store
from app.models.collections.receipt import Receipt
from app.models.collections.product import Product
from app.utils.auth_helper import token_required
from app.utils.gemini_receipt_analysis_helper import analyze_receipt_with_gemini
from app.utils.image_helper import optimize_image_stream, upload_receipt_to_drive
from app.utils.timezone import JST_TZ


TARGET_CITY = os.getenv("TARGET_CITY")


def penalize_user_for_bad_upload(user_id):
    try:
        User.penalize_user(user_id=user_id)
        print(f"Async penalty update for user {user_id} complete.")
    except Exception as e:
        print(f"Async penalty update failed for user {user_id}: {e}")


def reward_user_and_update_store(
    store_name,
    user_id,
    contribution_count=None,
    total_expenditure=None
):
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


def check_upload_permission(user_id):
    if not User.is_upload_allowed(user_id):
        response = Response(
            message_en="Uploads forbidden due to repeated bad uploads. Please try again in some time.",
            message_ja="不正なアップロードが繰り返されたため、アップロードは禁止されています。しばらくしてからもう一度お試しください。"
        )
        return response, 403
    return None, None


def validate_receipt_image():
    if 'receiptImage' not in request.files or request.files['receiptImage'].filename == '':
        response = Response(
            message_en="No receipt image provided.",
            message_ja="領収書の画像が提供されていません。"
        )
        return None, response, 400

    optimized_image_bytes = optimize_image_stream(request.files['receiptImage'])
    if not optimized_image_bytes:
        response = Response(
            message_en="Image processing failed.",
            message_ja="画像処理に失敗しました。"
        )
        return None, response, 400

    return optimized_image_bytes, None, None


def get_error_message(error_code):
    error_map = {
        1: {
            "en": "This image does not appear to be a receipt. Please upload a valid receipt.",
            "ja": "この画像は領収書ではないようです。有効な領収書をアップロードしてください。"
        },
        2: {
            "en": "This receipt appears to be edited or tampered with. Please upload an original receipt.",
            "ja": "この領収書は編集または改ざんされているようです。元の領収書をアップロードしてください。"
        },
        3: {
            "en": "This receipt is more than 3 days old. Please upload receipts from recent purchases.",
            "ja": "このレシートは3日以上前のものです。最近の購入のレシートをアップロードしてください。"
        },
        4: {
            "en": "This store type is not supported. We only accept receipts from convenience stores and supermarkets.",
            "ja": "この店舗タイプはサポートされていません。コンビニエンスストアまたはスーパーマーケットのレシートのみ受け付けております。"
        },
        5: {
            "en": "This store is not located in Sapporo.",
            "ja": "この店舗は札幌にはありません。"
        },
    }
    return error_map.get(
        error_code,
        {"en": "Invalid receipt.", "ja": "無効なレシートです。"}
    )


def analyze_receipt(optimized_image_bytes):
    available_stores = Store.get_all_store_names()

    now_utc = datetime.now(JST_TZ)
    valid_end_date = now_utc.strftime("%Y-%m-%d")
    valid_start_date = (now_utc - timedelta(days=3)).strftime("%Y-%m-%d")

    return analyze_receipt_with_gemini(
        optimized_image_bytes,
        TARGET_CITY,
        valid_start_date,
        valid_end_date,
        available_stores
    )


def handle_analysis_error(receipt_id, error_code, user_id):
    threading.Thread(
        target=penalize_user_for_bad_upload,
        args=(user_id,)
    ).start()

    err_obj = get_error_message(error_code)
    response = Response(
        message_en=err_obj["en"],
        message_ja=err_obj["ja"]
    )

    if receipt_id:
        Receipt.update_receipt_status(
            receipt_id,
            "FAILED",
            {"en": response.message_en, "ja": response.message_ja}
        )
    return jsonify(response.to_dict()), 400


def handle_no_products(receipt_id, user_id):
    threading.Thread(
        target=penalize_user_for_bad_upload,
        args=(user_id,)
    ).start()

    response = Response(
        message_en="No products found in receipt.",
        message_ja="レシートに商品が見つかりませんでした。"
    )

    if receipt_id:
        Receipt.update_receipt_status(
            receipt_id,
            "FAILED",
            {"en": response.message_en, "ja": response.message_ja}
        )
    return jsonify(response.to_dict()), 400


def process_successful_receipt(
    store_name,
    user_id,
    products,
    total_amount,
    purchase_date_str
):
    threading.Thread(
        target=reward_user_and_update_store,
        args=(store_name, user_id, len(products), float(total_amount))
    ).start()

    try:
        purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d").replace(tzinfo=JST_TZ)
    except (ValueError, TypeError):
        purchase_date = datetime.now(JST_TZ) - timedelta(days=3)

    response = Response(
        errorStatus=0,
        message_en="Receipt processed successfully!",
        message_ja="レシートの処理が完了しました！"
    )

    return purchase_date, response


@token_required
def add_or_update_product_details(current_user):
    user_id = str(current_user['_id'])

    try:
        response, status = check_upload_permission(user_id)
        if response:
            return jsonify(response.to_dict()), status

        receipt_id = Receipt.create_receipt(user_id)

        optimized_image_bytes, response, status = validate_receipt_image()
        if response:
            if receipt_id:
                Receipt.update_receipt_status(
                    receipt_id,
                    "FAILED",
                    {"en": response.message_en, "ja": response.message_ja}
                )
            return jsonify(response.to_dict()), status

        threading.Thread(
            target=upload_receipt_to_drive,
            args=(optimized_image_bytes, str(receipt_id))
        ).start()

        analysis_result = analyze_receipt(optimized_image_bytes)

        if not analysis_result:
            response = Response(
                message_en="Receipt Analysis failed. Please try again.",
                message_ja="レシート分析に失敗しました。もう一度お試しください。"
            )
            if receipt_id:
                Receipt.update_receipt_status(
                    receipt_id,
                    "FAILED",
                    {"en": response.message_en, "ja": response.message_ja}
                )
            return jsonify(response.to_dict()), 502

        error_code = analysis_result.get("error_code")

        if error_code != 0:
            return handle_analysis_error(receipt_id, error_code, user_id)

        purchase_date_str = analysis_result.get("purchase_date")
        store_name = analysis_result.get("store_name")
        store_identifier = analysis_result.get("store_identifier")
        total_amount = analysis_result.get("total_amount") or 0.0
        products = analysis_result.get("products") or []

        if not products:
            return handle_no_products(receipt_id, user_id)

        purchase_date, response = process_successful_receipt(
            store_name,
            user_id,
            products,
            total_amount,
            purchase_date_str
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
                products_found=products
            )

        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Product Update Error: {e}")
        return jsonify(
            Response(
                message_en="Internal server error.",
                message_ja="内部サーバーエラー。"
            ).to_dict()
        ), 500


@token_required
def get_all_products():
    try:
        products = Product.get_all_products()

        response = Response(
            errorStatus=0,
            message_en="Products fetched successfully.",
            message_ja="製品が正常に取得されました。",
            result={"products": products}
        )
        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Error fetching products: {e}")
        return jsonify(
            Response(
                message_en="Internal server error.",
                message_ja="内部サーバーエラー。"
            ).to_dict()
        ), 500


@token_required
def get_product_details():
    try:
        data = request.get_json() or {}
        product_ids = data.get('productIds', [])

        if not isinstance(product_ids, list):
            return jsonify(Response(message_en="Invalid input.", message_ja="無効な入力。").to_dict()), 400

        products_list = Product.get_products_by_ids(product_ids)

        stores_map = {}
        est_savings = 0.0

        for product in products_list:
            prices_data = product.get('prices', {})
            if not prices_data:
                continue

            max_price = 0.0
            store_prices = []
            for store_key, store_info in prices_data.items():
                price = float(store_info.get('price', 0))
                store_prices.append((store_key, price, store_info))
                if price > max_price:
                    max_price = price

            for store_key, store_price, store_info in store_prices:
                savings = max_price - store_price

                if store_key not in stores_map:
                    stores_map[store_key] = {
                        "name": store_key,
                        "products": [],
                        "savings": 0.0
                    }

                stores_map[store_key]["products"].append({
                    "name": product.get('name', ''),
                    "englishName": product.get('englishName', ''),
                    "price": store_price
                })
                stores_map[store_key]["savings"] += savings

                if stores_map[store_key]["savings"] > est_savings:
                    est_savings = stores_map[store_key]["savings"]

        result_stores = list(stores_map.values())

        response = Response(
            errorStatus=0,
            message_en="Product details fetched successfully.",
            message_ja="製品の詳細が正常に取得されました。",
            result={"stores": result_stores}
        )
        return jsonify(response.to_dict()), 200

    except Exception as e:
        print(f"Error calculating product details: {e}")
        return jsonify(
            Response(
                message_en="Internal server error.",
                message_ja="内部サーバーエラー。"
            ).to_dict()
        ), 500
