import os
import psycopg2
from psycopg2 import sql
from fastapi import FastAPI, Request
from pydantic import BaseModel
import httpx

app = FastAPI()

url_search = "https://prod-backoffice.daribar.com/api/v2/products/search"
url_price = "https://prod-backoffice.daribar.com/api/v2/delivery/prices"
params_city = {}
# Define the payload
payload = []

@app.post("/best_options")
async def main_process(request: Request):
    #Get City hash / sku's / user address
    # Receive the front end data (city hash, sku's, user address)
    request_data = await request.json()
    encoded_city = request_data.get("city")  # Encoded city hash
    sku_data = request_data.get("skus", [])  # List of SKU items
    address = request_data.get("address")  # User address
    token = request_data.get("token")  # Auth token if required

    # Validate the incoming data
    if not encoded_city or not sku_data:
        return {"error": "City and SKU data are required"}

     # Assuming sku_data is a list of dictionaries with 'sku' and 'count_desired'
    payload = [{"sku": item["sku"], "count_desired": item["count_desired"]} for item in sku_data]

    # Perform the search for medicines in pharmacies
    encoded_city = "%D0%90%D0%BB%D0%BC%D0%B0%D1%82%D1%8B&sort=recommended"
    pharmacies = find_medicines_in_pharmacies(encoded_city, payload)

    return {"pharmacies": pharmacies}


def decode_city():
    return 0

async def find_medicines_in_pharmacies(encoded_city, payload):
    async with httpx.AsyncClient() as client:
        response = await client.post(url_search, params=params_city, json=payload)
        return response.json()  # Return list of pharmacies with required medicines




def distance(user_adress,list_pharmacies):
    #Algorithm to determine distance between user and pharmacies

    return 0 #Return List of 3 pharmacies with shortest distance


def find_bucket_price():   
    #Search for cheapest sum of medicines in Pharmacies

    return 0 #Return 3 Pharmacies with cheapest price


def delivery_price():
    #POST request to /v2/products/delivery/prices

    #Check price of 3 closest pharmacies
    #Check price of 3 Pharmacies with cheapest price 
    return 0

def result():
    #Calculate cheapest total pharmacy / Calculate fastest Pharmacy


    #Return 1 cheapest / Return 1 fastest 
    return 0
