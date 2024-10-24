import json
import os
from datetime import datetime, timedelta
import pytz
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import logging
import math
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)
app = FastAPI()

URL_SEARCH = os.getenv("URL_SEARCH")
URL_PRICE = os.getenv("URL_PRICE")

# Define the payload
payload = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/best_options")
async def main_process(request: Request):
    # Receive the front end data (city hash, sku's, user address)
    request_data = await request.json()
    encoded_city = request_data.get("city")  # Encoded city hash
    sku_data = request_data.get("skus", [])  # List of SKU items
    address = request_data.get("address", {})  # User address


    #Save the latitude and longitude of user
    user_adress = request_data.get("address", {}).get("lng")
    user_lat = request_data.get("address", {}).get("lat")
    user_lon = request_data.get("address", {}).get("lng")
    
    # Validate the incoming data
    if not encoded_city or not sku_data or user_lat is None or user_lon is None:
        return {"error": "City, SKU data, and user coordinates are required"}
    if not encoded_city or not sku_data:
        return {"error": "City and SKU data are required"}

    # Build the payload
    payload = [{"sku": item["sku"], "count_desired": item["count_desired"]} for item in sku_data]

    # Perform the search for medicines in pharmacies
    pharmacies = await find_medicines_in_pharmacies(encoded_city, payload)
    no_variants = False

    #Save only pharmacies with all sku's in stock
    filtered_pharmacies = await filter_pharmacies(pharmacies)


    #If there is no pharmacy with full stock
    all_pharmacies_empty = not filtered_pharmacies.get("filtered_pharmacies")
    if all_pharmacies_empty:
        logger.info("No pharmacies")
        return 0

    #Get several pharmacies with cheapest sku's
    cheapest_pharmacies = await get_top_cheapest_pharmacies(filtered_pharmacies)
    save_response_to_file(cheapest_pharmacies, file_name='data4_top_cheapest_pharmacies.json')

    #Get 2 closest Pharmacies
    closest_pharmacies = await get_top_closest_pharmacies(filtered_pharmacies, user_lat, user_lon)
    save_response_to_file(closest_pharmacies, file_name='data4_top_closest_pharmacies.json')

    #Compare Check delivery price for 2 closest pharmacies and 3 cheapest pharmacies
    delivery_options1 = await get_delivery_options(closest_pharmacies, user_lat, user_lon)
    save_response_to_file(delivery_options1, file_name='data5_delivery_options_closest.json')

    delivery_options2 = await get_delivery_options(cheapest_pharmacies, user_lat, user_lon)
    save_response_to_file(delivery_options2, file_name='data5_delivery_options_cheapest.json')

    all_delivery_options = delivery_options1 + delivery_options2
    save_response_to_file(all_delivery_options, file_name='data5_all_delivery_options.json')

    result = await best_option(all_delivery_options)
    save_response_to_file(result, file_name='data6_final_result.json')

    return result


async def find_medicines_in_pharmacies(encoded_city, payload):
    async with httpx.AsyncClient() as client:
        response = await client.post(URL_SEARCH, params=encoded_city, json=payload)
        response.raise_for_status()  # Raise an error for bad responses
        save_response_to_file(response.json(), file_name='data1_found_all.json')
        return response.json()  # Return the JSON response


# мок для тестирования локальных результатов поиска
# async def find_medicines_in_pharmacies(encoded_city, payload):
#     async with httpx.AsyncClient() as client:
#         response = await client.get("http://localhost:8001/search_medicines")
#         response.raise_for_status()  # Проверка на ошибки
#         data = response.json()  # Получаем JSON
#         save_response_to_file(response.json(), file_name='data1_found_all.json')
#         return data  # Возвращаем JSON данные


#Save only pharmacies with all sku's in stock
async def filter_pharmacies(pharmacies):
    filtered_pharmacies = []

    for pharmacy in pharmacies.get("result", []):
        products = pharmacy.get("products", [])
        
        # Check if all products meet their desired quantities
        all_available = all(
            product["quantity"] >= product["quantity_desired"]
            for product in products if product["quantity_desired"] > 0
        )

        if all_available:
            filtered_pharmacies.append(pharmacy)

    save_response_to_file(filtered_pharmacies, file_name='data2_filtered_pharmacies.json')
    return {"filtered_pharmacies": filtered_pharmacies}


#Find pharmacies with cheapest "total_sum" fro sku's
async def get_top_cheapest_pharmacies(pharmacies):
    # Sort pharmacies by 'total_sum' in ascending order
    sorted_pharmacies = sorted(pharmacies.get("filtered_pharmacies", []), key=lambda x: x["total_sum"])

    # Get the top 3 pharmacies with the lowest 'total_sum'
    cheapest_pharmacies = sorted_pharmacies[:3]

    return {"list_pharmacies": cheapest_pharmacies}

async def get_top_closest_pharmacies(pharmacies, user_lat, user_lon):
    # Create a list of pharmacies with their distance from the user
    pharmacies_with_distance = []
    
    for pharmacy in pharmacies.get("filtered_pharmacies", []):
        pharmacy_lat = pharmacy["source"]["lat"]
        pharmacy_lon = pharmacy["source"]["lon"]
        
        # Calculate Euclidean distance
        distance = haversine_distance(user_lat, user_lon, pharmacy_lat, pharmacy_lon)
        
        # Add the pharmacy and its distance to the list
        pharmacies_with_distance.append({"pharmacy": pharmacy, "distance": distance})
    
    # Sort pharmacies by distance
    sorted_pharmacies = sorted(pharmacies_with_distance, key=lambda x: x["distance"])
    
    # Get the top 2 closest pharmacies
    closest_pharmacies = [item["pharmacy"] for item in sorted_pharmacies[:2]]
    
    return {"list_pharmacies": closest_pharmacies}


#Algorithm to determine distance in 2 dimensions
def haversine_distance(lat1, lon1, lat2, lon2):
    distance = math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2)
    return distance


def is_pharmacy_open_soon(closes_at, opening_hours):
    """Проверяет, закроется ли аптека через 1 час или позже, или если аптека работает круглосуточно."""
    almaty_tz = pytz.timezone('Asia/Almaty')
    current_time = datetime.now(almaty_tz)

    # мок для тестов локальных результатов поиска
    # current_time = almaty_tz.localize(datetime(2024, 10, 21, 22, 30, 0))

    # Проверка, если аптека круглосуточная
    if opening_hours == "Круглосуточно":
        return False  # Круглосуточная аптека не закроется скоро

    # Парсим время закрытия аптеки
    closes_time = datetime.strptime(closes_at, "%Y-%m-%dT%H:%M:%SZ")
    closes_time = closes_time.replace(tzinfo=pytz.UTC).astimezone(almaty_tz)
    # Если аптека закрывается через 1 час или меньше
    return closes_time - current_time <= timedelta(hours=1)


def is_pharmacy_closed(closes_at, opening_hours):
    """Проверяет, закрыта ли аптека на момент запроса."""
    almaty_tz = pytz.timezone('Asia/Almaty')
    current_time = datetime.now(almaty_tz)

    # мок для тестов локальных результатов поиска
    # current_time = almaty_tz.localize(datetime(2024, 10, 21, 22, 30, 0))

    # Проверка, если аптека круглосуточная
    if opening_hours == "Круглосуточно":
        return False  # Круглосуточная аптека никогда не закрыта

    closes_time = datetime.strptime(closes_at, "%Y-%m-%dT%H:%M:%SZ")
    closes_time = closes_time.replace(tzinfo=pytz.UTC).astimezone(almaty_tz)
    return current_time >= closes_time  # Если текущее время уже позже закрытия


async def get_delivery_options(pharmacies, user_lat, user_lon):
    """Функция возвращает все данные о доставке для аптек без принятия решений."""
    results = []

    for pharmacy in pharmacies["list_pharmacies"]:
        source = pharmacy.get("source", {})
        products = pharmacy.get("products", [])

        if "code" not in source:
            continue

        pharmacy_total_sum = pharmacy.get("total_sum", 0)

        # Формирование списка товаров с учетом оригиналов
        items = []
        for product in products:
            if product["quantity"] >= product["quantity_desired"]:
                items.append({"sku": product["sku"], "quantity": product["quantity_desired"]})

        if not items:
            continue

        # Формируем запрос для расчета доставки
        payload = {
            "items": items,
            "dst": {
                "lat": user_lat,
                "lng": user_lon
            },
            "source_code": source["code"]
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(URL_PRICE, json=payload)
                response.raise_for_status()
                delivery_data = response.json()

                if delivery_data.get("status") == "success":
                    delivery_options = delivery_data["result"]["delivery"]

                    for option in delivery_options:
                        results.append({
                            "pharmacy": pharmacy,
                            "total_price": pharmacy_total_sum + option["price"],
                            "delivery_option": option
                        })

            except httpx.RequestError as e:
                print(f"An error occurred while requesting {'URL_PRICE'}: {e}")
            except httpx.HTTPStatusError as e:
                print(f"Error response {e.response.status_code} while requesting {'URL_PRICE'}: {e}")

    return results


async def best_option(delivery_data):
    """Функция для сравнения аптек и выбора лучших опций с учетом времени закрытия, цены и условий."""

    cheapest_open_pharmacy = None
    cheapest_closed_pharmacy = None
    alternative_cheapest_option = None

    fastest_open_pharmacy = None
    fastest_closed_pharmacy = None
    alternative_fastest_option = None

    pharmacy_closes_soon = False
    pharmacy_closed = False

    for option in delivery_data:
        pharmacy = option.get("pharmacy", {})
        source = pharmacy.get("source", {})
        closes_at = source.get("closes_at")
        opening_hours = source.get("opening_hours", "")

        # Проверяем, что есть ключи 'code' и другие необходимые ключи перед использованием
        if 'code' not in source:
            logger.warning(f"Missing 'code' in pharmacy source: {source}")
            continue  # Пропускаем итерацию, если нет 'code'

        # Логика для проверки закрытых аптек и аптек, которые закроются через час
        if closes_at:
            pharmacy_closes_soon = is_pharmacy_open_soon(closes_at, opening_hours)
            pharmacy_closed = is_pharmacy_closed(closes_at, opening_hours)

        logger.info(
            f"Step 1: Checking pharmacy: {source['code']}, closes_at: {closes_at}, pharmacy_closes_soon: {pharmacy_closes_soon}, pharmacy_closed: {pharmacy_closed}, total_price: {option.get('total_price')}, eta: {option.get('delivery_option', {}).get('eta')}"
        )

        # Логика для самой дешевой аптеки
        if not pharmacy_closed:
            # Сохраняем самую дешевую открытую аптеку
            if cheapest_open_pharmacy is None or option["total_price"] < cheapest_open_pharmacy["total_price"]:
                logger.info(f"Step 2: Setting cheapest_open_pharmacy to {source['code']} with total_price {option['total_price']}")
                cheapest_open_pharmacy = option

                # Если аптека не закрывается скоро, не нужно альтернативы
                if not pharmacy_closes_soon:
                    logger.info(f"Step 3: Pharmacy {source['code']} works longer than 1 hour, resetting alternative_cheapest_option to None")
                    alternative_cheapest_option = None

            # Если аптека закрывается скоро, ищем альтернативу, которая не закрывается скоро
            if pharmacy_closes_soon:
                logger.info(f"Step 4: Pharmacy {source['code']} closes soon, looking for an alternative")
                # Ищем самую дешевую аптеку, которая не закрывается скоро
                if not alternative_cheapest_option:
                    for alt_option in delivery_data:
                        alt_pharmacy = alt_option.get("pharmacy", {})
                        alt_source = alt_pharmacy.get("source", {})
                        alt_closes_at = alt_source.get("closes_at")
                        alt_opening_hours = alt_source.get("opening_hours", "")

                        alt_pharmacy_closes_soon = is_pharmacy_open_soon(alt_closes_at, alt_opening_hours)
                        alt_pharmacy_closed = is_pharmacy_closed(alt_closes_at, alt_opening_hours)

                        # Логика для поиска самой дешевой альтернативы, которая не закрывается скоро
                        if not alt_pharmacy_closes_soon and not alt_pharmacy_closed and \
                                (alternative_cheapest_option is None or alt_option["total_price"] < alternative_cheapest_option["total_price"]):
                            logger.info(f"Step 5: Found alternative_cheapest_option with code {alt_source.get('code')}, works longer than 1 hour, and price {alt_option['total_price']}")
                            alternative_cheapest_option = alt_option

        else:
            # Если аптека закрыта, проверяем, дешевле ли она на 30% по сравнению с самой дешевой открытой
            if cheapest_open_pharmacy and option["total_price"] <= cheapest_open_pharmacy["total_price"] * 0.7:
                logger.info(f"difference: option['total_price']: {option['total_price']} cheapest_open_pharmacy * 0.7 = {cheapest_open_pharmacy['total_price'] * 0.7}")
                logger.info(f"Step 6: Closed pharmacy {source['code']} is 30% cheaper than the open one. Setting as cheapest_closed_pharmacy")
                cheapest_closed_pharmacy = option

        # Логика для самой быстрой аптеки
        if not pharmacy_closed:
            if fastest_open_pharmacy is None or option["delivery_option"]["eta"] < fastest_open_pharmacy["delivery_option"]["eta"]:
                logger.info(f"Step 2.1: Setting fastest_open_pharmacy to {source['code']} with eta {option['delivery_option']['eta']}")
                fastest_open_pharmacy = option

                # Если аптека не закрывается скоро, не нужно альтернативы
                if not pharmacy_closes_soon:
                    logger.info(f"Step 3.1: Pharmacy {source['code']} works longer than 1 hour, resetting alternative_fastest_option to None")
                    alternative_fastest_option = None

            # Если аптека закрывается скоро, ищем альтернативу, которая не закрывается скоро
            if pharmacy_closes_soon:
                logger.info(f"Step 4.1: Pharmacy {source['code']} closes soon, looking for an alternative fastest pharmacy")
                # Ищем самую быструю аптеку, которая не закрывается скоро
                if not alternative_fastest_option:
                    for alt_option in delivery_data:
                        alt_pharmacy = alt_option.get("pharmacy", {})
                        alt_source = alt_pharmacy.get("source", {})
                        alt_closes_at = alt_source.get("closes_at")
                        alt_opening_hours = alt_source.get("opening_hours", "")

                        alt_pharmacy_closes_soon = is_pharmacy_open_soon(alt_closes_at, alt_opening_hours)
                        alt_pharmacy_closed = is_pharmacy_closed(alt_closes_at, alt_opening_hours)

                        # Логика для поиска самой быстрой альтернативы, которая не закрывается скоро
                        if not alt_pharmacy_closes_soon and not alt_pharmacy_closed and \
                                (alternative_fastest_option is None or alt_option["delivery_option"]["eta"] < alternative_fastest_option["delivery_option"]["eta"]):
                            logger.info(f"Step 5.1: Found alternative_fastest_option with code {alt_source.get('code')}, works longer than 1 hour, and eta {alt_option['delivery_option']['eta']}")
                            alternative_fastest_option = alt_option

        else:
            # Если аптека закрыта, проверяем, быстрее ли она на 30% по сравнению с самой быстрой открытой
            if fastest_open_pharmacy and option["delivery_option"]["eta"] <= fastest_open_pharmacy["delivery_option"]["eta"] * 0.7:
                logger.info(f"Step 6.1: Closed pharmacy {source['code']} is 30% faster than the open one. Setting as fastest_closed_pharmacy")
                fastest_closed_pharmacy = option

    # Если найдена закрытая аптека с 30% скидкой, возвращаем её вместе с самой дешевой открытой
    if cheapest_closed_pharmacy and cheapest_open_pharmacy:
        logger.info("Step 7: Returning both cheapest open and cheapest closed pharmacies due to 30% discount")
        return {
            "cheapest_delivery_option": cheapest_open_pharmacy,
            "alternative_cheapest_option": cheapest_closed_pharmacy,
            "fastest_delivery_option": fastest_open_pharmacy,
            "alternative_fastest_option": fastest_closed_pharmacy
        }

    # Возвращаем стандартные результаты
    logger.info(f"Step 8: Returning the standard results with cheapest_open_pharmacy: {cheapest_open_pharmacy.get('pharmacy', {}).get('source', {}).get('code')}, fastest_open_pharmacy: {fastest_open_pharmacy.get('pharmacy', {}).get('source', {}).get('code')}")
    return {
        "cheapest_delivery_option": cheapest_open_pharmacy,
        "alternative_cheapest_option": alternative_cheapest_option,
        "fastest_delivery_option": fastest_open_pharmacy,
        "alternative_fastest_option": alternative_fastest_option
    }


#  функция для проверки выбранных на каждой стадии отбора аптек (сохраняет списки аптек в файлы локально)
def save_response_to_file(data, file_name='data.json'):
    try:
        # Сохраняем данные в файл
        with open(file_name, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

        print(f"Данные успешно сохранены в файл: {file_name}")
    except Exception as e:
        print(f"Ошибка при сохранении данных: {e}")


# мок ручки для возврата тестовых результатов запроса поиска аптек
@app.get("/search_medicines")
async def search_medicines():
    return JSONResponse(content={
        "result": [
        {
            "source": {
                "code": "apteka_sadyhan_3mkr_20a",
                "name": "Melissa Достык 42",
                "city": "Алматы",
                "address": "пр. Достык, 42",
                "lat": 43.242913,
                "lon": 76.877005,
                "opening_hours": "Пн-Вс: 08:00-00:00",
                "network_code": "melissa",
                "with_reserve": False,
                "payment_on_site": True,
                "kaspi_red": False,
                "closes_at": "2024-10-21T19:00:00Z",
                "opens_at": "2024-10-23T03:00:00Z",
                "source_tags": [
                    {
                        "id": 1045,
                        "meta": "5",
                        "color": "#000000",
                        "name": "public_client_time_to_confirmation"
                    },
                    {
                        "id": 1040,
                        "color": "#BFEA7C",
                        "name": "public_client_good_service"
                    }
                ],
                "working_today": True,
                "payment_by_card": False
            },
            "products": [
                {
                    "source_code": "apteka_sadyhan_3mkr_20a",
                    "sku": "dc12ea01-b677-45dc-89bd-127010638f86",
                    "name": "Доспрей спрей назальный 15 мл",
                    "base_price": 1000,
                    "price_with_warehouse_discount": 840,
                    "warehouse_discount": 0,
                    "quantity": 1,
                    "quantity_desired": 1,
                    "diff": 0,
                    "avg_price": 0,
                    "min_price": 0,
                    "pp_packing": "1 шт.",
                    "manufacturer_id": "ЛеКос ТОО",
                    "recipe_needed": True,
                    "strong_recipe": False
                },
                {
                    "source_code": "apteka_sadyhan_3mkr_20a",
                    "sku": "57d43666-20fd-4a46-bfe4-57cb7f8d43c9",
                    "name": "Виагра таблетки 100 мг №4",
                    "base_price": 2000,
                    "price_with_warehouse_discount": 27630,
                    "warehouse_discount": 0,
                    "quantity": 1,
                    "quantity_desired": 1,
                    "diff": 0,
                    "avg_price": 0,
                    "min_price": 0,
                    "pp_packing": "4 шт",
                    "manufacturer_id": "Фарева Амбуаз",
                    "recipe_needed": True,
                    "strong_recipe": False
                }
            ],
            "total_sum": 3000,
            "avg_sum": 14235,
            "min_sum": 840
        },
        {
            "source": {
                "code": "apteka_sadyhan_5mkr_19b",
                "name": "Аптека со склада Мкр 4, 30 (г.Кунаева)",
                "city": "Алматы",
                "address": "​4-й микрорайон, 30",
                "lat": 43.239826,
                "lon": 76.902216,
                "opening_hours": "Пн-Вс: 08:00-00:00",
                "network_code": "apteka_so_sklada_3",
                "with_reserve": True,
                "payment_on_site": True,
                "kaspi_red": False,
                "closes_at": "2024-10-21T19:00:00Z",
                "opens_at": "2024-10-23T03:00:00Z",
                "working_today": True,
                "payment_by_card": False
            },
            "products": [
                {
                    "source_code": "apteka_sadyhan_5mkr_19b",
                    "sku": "dc12ea01-b677-45dc-89bd-127010638f86",
                    "name": "Доспрей спрей назальный 15 мл",
                    "base_price": 1000,
                    "price_with_warehouse_discount": 685,
                    "warehouse_discount": 0,
                    "quantity": 1,
                    "quantity_desired": 1,
                    "diff": 0,
                    "avg_price": 0,
                    "min_price": 0,
                    "pp_packing": "1 шт.",
                    "manufacturer_id": "ЛеКос ТОО",
                    "recipe_needed": True,
                    "strong_recipe": False
                },
                {
                    "source_code": "apteka_sadyhan_5mkr_19b",
                    "sku": "57d43666-20fd-4a46-bfe4-57cb7f8d43c9",
                    "name": "Виагра таблетки 100 мг №4",
                    "base_price": 3000,
                    "price_with_warehouse_discount": 19700,
                    "warehouse_discount": 0,
                    "quantity": 1,
                    "quantity_desired": 1,
                    "diff": 0,
                    "avg_price": 0,
                    "min_price": 0,
                    "pp_packing": "4 шт",
                    "manufacturer_id": "Фарева Амбуаз",
                    "recipe_needed": True,
                    "strong_recipe": False
                }
            ],
            "total_sum": 4000,
            "avg_sum": 10193,
            "min_sum": 685
        },
        {
            "source": {
                "code": "apteka_sadyhan_almaty_satpaeva_90_20",
                "name": "Аптека со склада Мкр Коктем1 д 16",
                "city": "Алматы",
                "address": "Микрорайон Коктем-1, 16",
                "lat": 43.264685,
                "lon": 76.950991,
                "opening_hours": "Пн-Вс: 08:00-00:00",
                "network_code": "apteka_so_sklada",
                "with_reserve": True,
                "payment_on_site": True,
                "kaspi_red": False,
                "closes_at": "2024-10-21T19:00:00Z",
                "opens_at": "2024-10-23T03:00:00Z",
                "working_today": True,
                "payment_by_card": False
            },
            "products": [
                {
                    "source_code": "apteka_sadyhan_almaty_satpaeva_90_20",
                    "sku": "dc12ea01-b677-45dc-89bd-127010638f86",
                    "name": "Доспрей спрей назальный 15 мл",
                    "base_price": 1000,
                    "price_with_warehouse_discount": 695,
                    "warehouse_discount": 0,
                    "quantity": 1,
                    "quantity_desired": 1,
                    "diff": 0,
                    "avg_price": 0,
                    "min_price": 0,
                    "pp_packing": "1 шт.",
                    "manufacturer_id": "ЛеКос ТОО",
                    "recipe_needed": True,
                    "strong_recipe": False
                },
                {
                    "source_code": "apteka_sadyhan_almaty_satpaeva_90_20",
                    "sku": "57d43666-20fd-4a46-bfe4-57cb7f8d43c9",
                    "name": "Виагра таблетки 100 мг №4",
                    "base_price": 40,
                    "price_with_warehouse_discount": 20010,
                    "warehouse_discount": 0,
                    "quantity": 1,
                    "quantity_desired": 1,
                    "diff": 0,
                    "avg_price": 0,
                    "min_price": 0,
                    "pp_packing": "4 шт",
                    "manufacturer_id": "Фарева Амбуаз",
                    "recipe_needed": True,
                    "strong_recipe": False
                }
            ],
            "total_sum": 5000,
            "avg_sum": 10353,
            "min_sum": 695
        }
        ]
    })
