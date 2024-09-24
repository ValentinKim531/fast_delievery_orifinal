import os
import psycopg2
from psycopg2 import sql
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Define Pydantic Model for Product Data
class ProductData(BaseModel):
    sku: str
    categories: str
    service_name: str
    manufacturer: str
    min_customer_price: int
    avg_customer_price: int
    max_customer_price: int
    quantity: int
    city: str
    url_key: str

# Database connection parameters (these will come from Railway's environment)
DB_HOST = os.getenv('PGHOST', 'localhost')
DB_NAME = os.getenv('PGDATABASE', 'postgres')
DB_USER = os.getenv('PGUSER', 'postgres')
DB_PASSWORD = os.getenv('PGPASSWORD', 'password')
DB_PORT = os.getenv('PGPORT', '5432')

def connect_to_db():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        print("Connected to the database")
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

@app.post("/create_table")
def create_table():
    conn = connect_to_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS product_table (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(255),
                categories VARCHAR(255),
                service_name VARCHAR(255),
                manufacturer VARCHAR(255),
                min_customer_price INT,
                avg_customer_price INT,
                max_customer_price INT,
                quantity INT,
                city VARCHAR(255),
                url_key TEXT
            );''')
            conn.commit()
            print("Table created")
            return {"message": "Table created successfully"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

@app.post("/insert_data/")
def insert_data(product: ProductData):
    conn = connect_to_db()
    if conn:
        try:
            cur = conn.cursor()
            print(f"Inserting data for SKU {product.sku}")  # Log the SKU
            cur.execute("""
                INSERT INTO product_table 
                (sku, categories, service_name, manufacturer, 
                min_customer_price, avg_customer_price, max_customer_price, 
                quantity, city, url_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (product.sku, product.categories, product.service_name, product.manufacturer, 
                  product.min_customer_price, product.avg_customer_price, product.max_customer_price, 
                  product.quantity, product.city, product.url_key))
            conn.commit()
            print("Data successfully inserted.")  # Log the insertion
            # Return the inserted product data in the response
            return {"message": "Data inserted successfully", "data": product.dict()}
        except Exception as e:
            print(f"Error during insertion: {str(e)}")  # Log any errors
            return {"error": str(e)}
        finally:
            conn.close()


@app.get("/get_data")
def get_data():
    conn = connect_to_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM product_table;")
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    "id": row[0],
                    "sku": row[1],
                    "categories": row[2],
                    "service_name": row[3],
                    "manufacturer": row[4],
                    "min_customer_price": row[5],
                    "avg_customer_price": row[6],
                    "max_customer_price": row[7],
                    "quantity": row[8],
                    "city": row[9],
                    "url_key": row[10]
                })
            return {"data": result}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

@app.get("/")
def root():
    return {"message": "Welcome to the PostgreSQL FastAPI app!"}
