import os
import psycopg2
from psycopg2 import sql
from fastapi import FastAPI, Request
from pydantic import BaseModel
import httpx
import logging
import math

logging.basicConfig(level=logging.INFO)  # You can adjust the level as needed
logger = logging.getLogger(__name__)
app = FastAPI()

url_search = "https://prod-backoffice.daribar.com/api/v2/products/search"
url_price = "https://prod-backoffice.daribar.com/api/v2/delivery/prices"
params_city = {}
# Define the payload
payload = []

@app.post("/best_options")
async def main_process(request: Request):
    # Receive the front end data (city hash, sku's, user address)
    request_data = await request.json()
    encoded_city = request_data.get("city")  # Encoded city hash
    sku_data = request_data.get("skus", [])  # List of SKU items
    address = request_data.get("address", {})  # User address
    token = request_data.get("token")  # Auth token if required

    logger.info("City: %s, SKU Data: %s", encoded_city, sku_data)
    logger.info("Address: %s", address)

    #Save the latitude and longitude of user
    user_lat = request_data.get("address", {}).get("lat")
    user_lon = request_data.get("address", {}).get("lng")
    logger.info("You sure: lat: %s  lon : %s", user_lat, user_lon)
    
    # Validate the incoming data
    if not encoded_city or not sku_data or user_lat is None or user_lon is None:
        return {"error": "City, SKU data, and user coordinates are required"}
    if not encoded_city or not sku_data:
        return {"error": "City and SKU data are required"}

    # Build the payload
    payload = [{"sku": item["sku"], "count_desired": item["count_desired"]} for item in sku_data]

    # Perform the search for medicines in pharmacies
    pharmacies = await find_medicines_in_pharmacies(encoded_city, payload)

    #Save only pharmacies with all sku's in stock
    filtered_pharmacies = await filter_pharmacies(pharmacies)

    #Get several pharmacies with cheapest sku's
    cheapest_pharmacies = await get_top_cheapest_pharmacies(filtered_pharmacies)

    closest_pharmacies = await get_top_closest_pharmacies(filtered_pharmacies, user_lat, user_lon)

    return {"pharmacies": closest_pharmacies}




async def find_medicines_in_pharmacies(encoded_city, payload):
    async with httpx.AsyncClient() as client:
        response = await client.post(url_search, params=params_city, json=payload)
        response.raise_for_status()  # Raise an error for bad responses
        return response.json()  # Return the JSON response


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

    return {"filtered_pharmacies": filtered_pharmacies}


#Find pharmacies with cheapest "total_sum" fro sku's
async def get_top_cheapest_pharmacies(pharmacies):
    # Sort pharmacies by 'total_sum' in ascending order
    sorted_pharmacies = sorted(pharmacies.get("filtered_pharmacies", []), key=lambda x: x["total_sum"])

    # Get the top 5 pharmacies with the lowest 'total_sum'
    top_5_pharmacies = sorted_pharmacies[:5]

    return {"cheapest_pharmacies": top_5_pharmacies}

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
    
    # Get the top 5 closest pharmacies
    top_5_pharmacies = [item["pharmacy"] for item in sorted_pharmacies[:5]]
    
    return {"closest_pharmacies": top_5_pharmacies}


#Algorithm to determine distance in 2 dimensions
def haversine_distance(lat1, lon1, lat2, lon2):
    distance = math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2)
    return distance


def delivery_price():
    #POST request to /v2/products/delivery/prices

    #Check price of 3 closest pharmacies
    #Check price of 3 Pharmacies with cheapest price 
    return 0

def result():
    #Calculate cheapest total pharmacy / Calculate fastest Pharmacy


    #Return 1 cheapest / Return 1 fastest 
    return 0
