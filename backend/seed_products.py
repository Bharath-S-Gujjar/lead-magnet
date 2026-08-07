import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db = client["leadmagnet"]
products = db["products"]

products.delete_many({})  # clear any old seed data

sample_products = [
    {"name": "Classic Tee", "category": "men", "price": 19.99, "size": ["S", "M", "L"], "color": "black"},
    {"name": "Summer Dress", "category": "women", "price": 34.99, "size": ["S", "M"], "color": "blue"},
    {"name": "Kids Hoodie", "category": "kids", "price": 24.99, "size": ["XS", "S"], "color": "red"},
    {"name": "Denim Jacket", "category": "men", "price": 49.99, "size": ["M", "L", "XL"], "color": "blue"},
    {"name": "Running Shoes", "category": "women", "price": 59.99, "size": ["6", "7", "8"], "color": "white"},
]

products.insert_many(sample_products)
print(f"Inserted {len(sample_products)} products")