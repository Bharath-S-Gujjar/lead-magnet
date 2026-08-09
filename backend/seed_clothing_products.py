import os
from pathlib import Path
from dotenv import load_dotenv

PRODUCT_GROUPS = [
    ("Men", "T-Shirts", ["Roadster", "HRX", "Bewakoof", "Jack & Jones"], (499, 1499)),
    ("Men", "Shirts", ["Allen Solly", "Peter England", "Louis Philippe", "Van Heusen"], (899, 2499)),
    ("Men", "Jeans", ["Levi's", "Spykar", "Pepe Jeans", "Mufti"], (1499, 3999)),
    ("Men", "Trousers", ["Park Avenue", "Raymond", "Arrow", "Blackberrys"], (1299, 3499)),
    ("Men", "Hoodies", ["HRX", "Puma", "Campus Sutra", "Wrogn"], (999, 2999)),
    ("Men", "Jackets", ["Fort Collins", "Roadster", "U.S. Polo Assn.", "Woodland"], (1999, 5999)),
    ("Men", "Ethnic Wear", ["Manyavar", "Fabindia", "Sojanya", "Ethnix"], (1299, 4999)),
    ("Women", "Dresses", ["Tokyo Talkies", "AND", "Vero Moda", "Global Desi"], (899, 3499)),
    ("Women", "Kurtas", ["Biba", "Aurelia", "W", "Libas"], (699, 2499)),
    ("Women", "Sarees", ["Sangria", "Indya", "Soch", "Nalli"], (1299, 7999)),
    ("Women", "Tops", ["ONLY", "DressBerry", "H&M", "MANGO"], (499, 2299)),
    ("Women", "Jeans", ["Levi's", "ONLY", "Lee Cooper", "Flying Machine"], (1299, 3999)),
    ("Women", "Ethnic Wear", ["Biba", "Global Desi", "W", "Fabindia"], (999, 4499)),
    ("Women", "Jackets", ["Vero Moda", "ONLY", "Zara", "Mast & Harbour"], (1499, 5999)),
    ("Kids", "Boys", ["Gini & Jony", "U.S. Polo Assn. Kids", "Max Kids", "Hopscotch"], (399, 1799)),
    ("Kids", "Girls", ["Peppermint", "Cutecumber", "Max Kids", "Hopscotch"], (399, 1999)),
    ("Kids", "Infant", ["Mothercare", "FirstCry", "Babyhug", "H&M Kids"], (299, 1499)),
]

STYLE_WORDS = [
    "Classic", "Premium", "Casual", "Slim Fit", "Regular Fit", "Printed",
    "Solid", "Festive", "Cotton", "Denim", "Linen", "Comfort",
]


def generate_products():
    products = []
    for group_index, (gender, category, brands, price_range) in enumerate(PRODUCT_GROUPS):
        for item_index in range(4):
            brand = brands[item_index % len(brands)]
            style = STYLE_WORDS[(group_index + item_index) % len(STYLE_WORDS)]
            price = price_range[0] + ((price_range[1] - price_range[0]) // 5) * (item_index + 1)
            name = f"{brand} {style} {category}"
            products.append({
                "name": name,
                "category": category,
                "gender": gender,
                "brand": brand,
                "price": int(price),
                "image": f"https://via.placeholder.com/600x800?text={brand.replace(' ', '+')}+{category.replace(' ', '+')}",
                "stock": 25 + (group_index * 3) + item_index,
                "description": f"{style} {category.lower()} by {brand}, selected for Indian clothing shoppers.",
                "tags": [
                    gender.lower(),
                    category.lower().replace(" ", "-"),
                    brand.lower().replace(" ", "-"),
                    style.lower().replace(" ", "-"),
                ],
                "rating": round(4.1 + ((item_index % 4) * 0.2), 1),
                "discount": [0, 10, 15, 20][item_index % 4],
            })
    return products


def seed_clothing_products_if_empty(products_collection):
    if products_collection.count_documents({}) > 0:
        return 0, 0

    products = generate_products()
    inserted = 0
    updated = 0

    for product in products:
        result = products_collection.update_one(
            {"name": product["name"], "brand": product["brand"]},
            {"$setOnInsert": product},
            upsert=True,
        )
        if result.upserted_id:
            inserted += 1
        else:
            updated += 1

    print(f"Products seeded automatically. Inserted: {inserted}, Already present: {updated}")
    return inserted, updated


if __name__ == "__main__":
    import certifi
    from pymongo import MongoClient

    load_dotenv(Path(__file__).with_name(".env"))
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI is required")

    if mongo_uri.startswith("mongodb://localhost") or mongo_uri.startswith("mongodb://127.0.0.1"):
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    else:
        client = MongoClient(
            mongo_uri,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
        )
    col = client["leadmagnet"]["products"]
    seed_clothing_products_if_empty(col)
