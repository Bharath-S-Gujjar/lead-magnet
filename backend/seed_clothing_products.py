import os
from pathlib import Path
from dotenv import load_dotenv

PRODUCT_GROUPS = [
    # Men
    ("Men", "Shirts", ["Allen Solly", "Peter England", "Louis Philippe", "Van Heusen", "Arrow", "Park Avenue", "Raymond", "Blackberrys"], (899, 2499)),
    ("Men", "T-Shirts", ["Roadster", "HRX", "Bewakoof", "Jack & Jones", "Puma", "Nike", "U.S. Polo Assn.", "Levi's"], (499, 1499)),
    ("Men", "Jeans", ["Levi's", "Spykar", "Pepe Jeans", "Mufti", "Wrangler", "Lee", "Flying Machine", "Jack & Jones"], (1499, 3999)),
    ("Men", "Hoodies", ["HRX", "Puma", "Campus Sutra", "Wrogn", "Roadster", "Nike", "Adidas", "Fort Collins"], (999, 2999)),
    ("Men", "Jackets", ["Fort Collins", "Roadster", "U.S. Polo Assn.", "Woodland", "Wildcraft", "Columbia", "Puma", "Superdry"], (1999, 5999)),
    ("Men", "Kurtas", ["Manyavar", "Fabindia", "Sojanya", "Ethnix", "Tasva", "Sanwara", "Deyann", "Vastramay"], (1299, 4999)),

    # Women
    ("Women", "Dresses", ["Tokyo Talkies", "AND", "Vero Moda", "Global Desi", "MANGO", "ONLY", "Forever 21", "Zara"], (899, 3499)),
    ("Women", "Sarees", ["Sangria", "Indya", "Soch", "Nalli", "Sabyasachi", "Kalamandir", "Mimosa", "Craftsvilla"], (1299, 7999)),
    ("Women", "Kurtis", ["Biba", "Aurelia", "W", "Libas", "Jaipur Kurti", "Anouk", "Sangria", "Rangriti"], (699, 2499)),
    ("Women", "Tops", ["ONLY", "DressBerry", "H&M", "MANGO", "Vero Moda", "StyleCast", "Tokyo Talkies", "Roadster"], (499, 2299)),
    ("Women", "Jeans", ["Levi's", "ONLY", "Lee Cooper", "Flying Machine", "Pepe Jeans", "Kraus Jeans", "Roadster", "High Star"], (1299, 3999)),
    ("Women", "Ethnic Wear", ["Biba", "Global Desi", "W", "Fabindia", "Indya", "Ritu Kumar", "Anita Dongre", "Soch"], (999, 4499)),

    # Kids
    ("Kids", "T-Shirts", ["Gini & Jony", "U.S. Polo Assn. Kids", "Max Kids", "Hopscotch", "Mothercare", "H&M Kids", "FirstCry", "Puma Kids"], (399, 1499)),
    ("Kids", "Dresses", ["Peppermint", "Cutecumber", "Max Kids", "Hopscotch", "Mothercare", "Gini & Jony", "FirstCry", "Nauti Nati"], (499, 1999)),
    ("Kids", "Shorts", ["Gini & Jony", "Max Kids", "Hopscotch", "U.S. Polo Assn. Kids", "Mothercare", "H&M Kids", "Puma Kids", "FirstCry"], (349, 1299)),
    ("Kids", "Hoodies", ["Mothercare", "FirstCry", "Babyhug", "H&M Kids", "Max Kids", "Gini & Jony", "Hopscotch", "Puma Kids"], (599, 1799)),
]

STYLE_WORDS = [
    "Classic", "Premium", "Casual", "Slim Fit", "Regular Fit", "Printed",
    "Solid", "Festive", "Cotton", "Denim", "Linen", "Comfort", "Designer", "Urban",
]

UNSPLASH_IMAGES = {
    ("Men", "Shirts"): [
        "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1621072156002-e2fccdc0b176?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=600&auto=format&fit=crop",
    ],
    ("Men", "T-Shirts"): [
        "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=600&auto=format&fit=crop",
    ],
    ("Men", "Jeans"): [
        "https://images.unsplash.com/photo-1542272604-780c36856842?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=600&auto=format&fit=crop",
    ],
    ("Men", "Hoodies"): [
        "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1509967419530-da38b4704bc6?w=600&auto=format&fit=crop",
    ],
    ("Men", "Jackets"): [
        "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1548883354-7622d03aca27?w=600&auto=format&fit=crop",
    ],
    ("Men", "Kurtas"): [
        "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=600&auto=format&fit=crop",
    ],
    ("Women", "Dresses"): [
        "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1539109136881-3be0616acf4b?w=600&auto=format&fit=crop",
    ],
    ("Women", "Sarees"): [
        "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1617627143750-d86bc21e42bb?w=600&auto=format&fit=crop",
    ],
    ("Women", "Kurtis"): [
        "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1617627143750-d86bc21e42bb?w=600&auto=format&fit=crop",
    ],
    ("Women", "Tops"): [
        "https://images.unsplash.com/photo-1564257631407-4deb1f99d992?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?w=600&auto=format&fit=crop",
    ],
    ("Women", "Jeans"): [
        "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=600&auto=format&fit=crop",
    ],
    ("Women", "Ethnic Wear"): [
        "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=600&auto=format&fit=crop",
    ],
    ("Kids", "T-Shirts"): [
        "https://images.unsplash.com/photo-1519238263530-99bdd11df2ea?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1622290291468-a28f7a7dc6a8?w=600&auto=format&fit=crop",
    ],
    ("Kids", "Dresses"): [
        "https://images.unsplash.com/photo-1621452773781-0f992fd1f5cb?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1518831959646-742c3a14ebf7?w=600&auto=format&fit=crop",
    ],
    ("Kids", "Shorts"): [
        "https://images.unsplash.com/photo-1503944583220-79d8926ad5e2?w=600&auto=format&fit=crop",
    ],
    ("Kids", "Hoodies"): [
        "https://images.unsplash.com/photo-1519238263530-99bdd11df2ea?w=600&auto=format&fit=crop",
    ],
}


def generate_products():
    products = []
    for group_index, (gender, category, brands, price_range) in enumerate(PRODUCT_GROUPS):
        images = UNSPLASH_IMAGES.get((gender, category), [
            "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=600&auto=format&fit=crop"
        ])
        for item_index in range(8):
            brand = brands[item_index % len(brands)]
            style = STYLE_WORDS[(group_index * 3 + item_index) % len(STYLE_WORDS)]
            price = price_range[0] + ((price_range[1] - price_range[0]) // 8) * (item_index + 1)
            name = f"{brand} {style} {category}"
            img = images[item_index % len(images)]
            products.append({
                "name": name,
                "category": category,
                "gender": gender,
                "brand": brand,
                "price": int(price),
                "image": img,
                "stock": 15 + (group_index * 2) + item_index,
                "description": f"{style} {category.lower()} by {brand}, premium design for Indian shoppers.",
                "tags": [
                    gender.lower(),
                    category.lower().replace(" ", "-"),
                    brand.lower().replace(" ", "-"),
                    style.lower().replace(" ", "-"),
                ],
                "rating": round(4.0 + ((item_index % 5) * 0.2), 1),
                "discount": [0, 10, 15, 20, 25][item_index % 5],
            })
    return products


def seed_clothing_products_if_empty(products_collection):
    current_count = products_collection.count_documents({})
    if current_count >= 120:
        return 0, current_count

    products = generate_products()
    inserted = 0
    updated = 0

    for product in products:
        result = products_collection.update_one(
            {"name": product["name"], "brand": product["brand"]},
            {"$set": product},
            upsert=True,
        )
        if result.upserted_id:
            inserted += 1
        else:
            updated += 1

    print(f"Products seeded. Total products in database: {products_collection.count_documents({})}. Inserted: {inserted}, Updated: {updated}")
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
