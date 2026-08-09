import os
from pathlib import Path

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv(Path(__file__).with_name(".env"))

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is required")


def connect_mongo(uri):
    # Attempt 1: Standard
    try:
        c = MongoClient(uri, serverSelectionTimeoutMS=5000)
        c.admin.command("ping")
        return c
    except Exception:
        pass
    # Attempt 2: certifi CA file
    try:
        c = MongoClient(uri, tls=True, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        c.admin.command("ping")
        return c
    except Exception:
        pass
    # Attempt 3: tlsAllowInvalidCertificates
    return MongoClient(uri, tls=True, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=5000)


client = connect_mongo(MONGO_URI)
db = client["leadmagnet"]
products = db["products"]

seed_products = [
    {
        "name": "Men Classic Cotton Shirt",
        "description": "Regular-fit cotton shirt for everyday wear.",
        "category": "shirts",
        "gender": "men",
        "brand": "Lead Magnet Clothing",
        "price": 1299,
        "images": ["https://via.placeholder.com/600x800?text=Men+Cotton+Shirt"],
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["White", "Blue"],
        "stock": 40,
    },
    {
        "name": "Women Floral Summer Dress",
        "description": "Lightweight floral dress with a relaxed silhouette.",
        "category": "dresses",
        "gender": "women",
        "brand": "Lead Magnet Clothing",
        "price": 1899,
        "images": ["https://via.placeholder.com/600x800?text=Floral+Dress"],
        "sizes": ["S", "M", "L"],
        "colors": ["Pink", "Yellow"],
        "stock": 32,
    },
    {
        "name": "Kids Graphic T-Shirt",
        "description": "Soft cotton graphic t-shirt for kids.",
        "category": "kids",
        "gender": "kids",
        "brand": "Lead Magnet Clothing",
        "price": 699,
        "images": ["https://via.placeholder.com/600x800?text=Kids+T-Shirt"],
        "sizes": ["2-3Y", "4-5Y", "6-7Y"],
        "colors": ["Red", "Navy"],
        "stock": 55,
    },
    {
        "name": "Women Embroidered Kurta",
        "description": "Elegant embroidered kurta for casual and festive wear.",
        "category": "kurtas",
        "gender": "women",
        "brand": "Lead Magnet Clothing",
        "price": 1499,
        "images": ["https://via.placeholder.com/600x800?text=Embroidered+Kurta"],
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["Green", "Maroon"],
        "stock": 36,
    },
    {
        "name": "Men Slim Fit Jeans",
        "description": "Stretch denim jeans with a slim fit.",
        "category": "jeans",
        "gender": "men",
        "brand": "Lead Magnet Clothing",
        "price": 2199,
        "images": ["https://via.placeholder.com/600x800?text=Men+Jeans"],
        "sizes": ["30", "32", "34", "36"],
        "colors": ["Blue", "Black"],
        "stock": 28,
    },
    {
        "name": "Women High Rise Jeans",
        "description": "High-rise denim jeans with a tapered leg.",
        "category": "jeans",
        "gender": "women",
        "brand": "Lead Magnet Clothing",
        "price": 2299,
        "images": ["https://via.placeholder.com/600x800?text=Women+Jeans"],
        "sizes": ["26", "28", "30", "32"],
        "colors": ["Blue", "Grey"],
        "stock": 24,
    },
    {
        "name": "Men Everyday T-Shirt",
        "description": "Breathable crew-neck t-shirt for daily use.",
        "category": "t-shirts",
        "gender": "men",
        "brand": "Lead Magnet Clothing",
        "price": 799,
        "images": ["https://via.placeholder.com/600x800?text=Men+T-Shirt"],
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["Black", "Olive"],
        "stock": 60,
    },
    {
        "name": "Kids Denim Jeans",
        "description": "Durable denim jeans designed for kids.",
        "category": "kids",
        "gender": "kids",
        "brand": "Lead Magnet Clothing",
        "price": 999,
        "images": ["https://via.placeholder.com/600x800?text=Kids+Jeans"],
        "sizes": ["2-3Y", "4-5Y", "6-7Y", "8-9Y"],
        "colors": ["Blue"],
        "stock": 42,
    },
]

inserted = 0
updated = 0

for product in seed_products:
    result = products.update_one(
        {"name": product["name"]},
        {"$set": product},
        upsert=True,
    )
    if result.upserted_id:
        inserted += 1
    elif result.modified_count:
        updated += 1

print(f"Seed complete: {inserted} inserted, {updated} updated")
