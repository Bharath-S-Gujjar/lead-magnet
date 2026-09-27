import sys
import os
sys.path.insert(0, '.')
sys.path.insert(0, 'scripts')
import re
import hashlib
import json
import csv
from collections import Counter, defaultdict

# Adjust path for parsing
from inspect_raw_data import parse_full_xlsx

CATEGORY_RULES = [
    ('T-Shirts', r'(t-?shirts?|tees?|polos?|\btee\b)'),
    ('Shirts', r'(casualshirt|formalshirt|shirts?)'),
    ('Kurtas & Kurta Sets', r'(printedkurta|kurtas?|kurtis?|anarkali|kurta\s*sets?|sherwanis?)'),
    ('Dresses & Jumpsuits', r'(dress(es)?|frocks?|gowns?|jumpsuits?|rompers?|playsuits?|maxi)'),
    ('Tops & Tunics', r'(tops?|tunics?|blouses?|camisoles?)'),
    ('Jeans', r'(jeans?|denims?|eans\b)'),
    ('Trousers & Pants', r'(trousers?|chinos?|pants?|cargos?|bottoms?)'),
    ('Track Pants & Joggers', r'(track\s*pants?|joggers?|sweatpants?)'),
    ('Sweaters & Sweatshirts', r'(sweaters?|sweatshirts?|cardigans?|pullovers?|hoodies?|jumpers?|ponchos?|cable\s*knit)'),
    ('Jackets & Coats', r'(jackets?|coats?|blazers?|shrugs?|waistcoats?|bomber|raincoats?|shackets?)'),
    ('Shorts', r'(shorts?)'),
    ('Skirts', r'(skirts?|skorts?)'),
    ('Sarees', r'(sarees?|saris?)'),
    ('Leggings & Churidars', r'(leggings?|jeggings?|tights?|churidars?|palazzos?)'),
    ('Ethnic Wear', r'(lehengas?|dupattas?|salwars?|nehru\s*jackets?|dhotis?|ethnic)'),
    ('Nightwear & Loungewear', r'(nightdress|night\s*suits?|pyjamas?|pajamas?|sleepwear|loungewear|lounge\s*pants?|lounge\s*wear|robes?)'),
    ('Innerwear & Sleepwear', r'(bras?|briefs?|boxers?|panties?|trunks?|vests?|lingerie|innerwear|thermals?|thongs?|innervest)'),
    ('Co-ords & Clothing Sets', r'(co-?ords?|tracksuits?|clothing\s*sets?|dungarees?|\bsuits?\b)'),
    ('Swimwear', r'(swimsuits?|swimwears?|bikinis?)'),
    ('Footwear', r'(shoes?|sneakers?|sandals?|flats?|heels?|boots?|slippers?|flip\s*flops?|loafers?|ballerinas?)'),
    ('Accessories', r'(belts?|caps?|hats?|socks?|scarfs?|scarves?|sunglasses?|wallets?|bags?|backpacks?|ties?|watches?|tiaras?)'),
]

def extract_category(name):
    if not name:
        return 'Other Clothing'
    n = name.lower()
    for cat, pattern in CATEGORY_RULES:
        if re.search(pattern, n):
            return cat
    return 'Other Clothing'

def parse_price(val):
    if not val:
        return None
    s = str(val).replace(',', '').strip()
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    return float(m.group(1)) if m else None

def parse_discount(val, price=None):
    if not val:
        return None
    s = str(val).strip()
    m_pct = re.search(r'(\d+(?:\.\d+)?)\s*%', s)
    if m_pct:
        return float(m_pct.group(1))
    m_flat = re.search(r'Rs\.?\s*(\d+(?:\.\d+)?)', s)
    if m_flat and price and price > 0:
        flat_off = float(m_flat.group(1))
        original_price = price + flat_off
        return round((flat_off / original_price) * 100.0, 1)
    return None

def parse_rating(val):
    if not val:
        return None
    try:
        r = float(val)
        if 1.0 <= r <= 5.0:
            return round(r, 1)
    except ValueError:
        pass
    return None

def parse_buyers(val):
    if not val:
        return None
    s = str(val).strip().lower()
    if 'k' in s:
        num_part = re.sub(r'[^\d.]', '', s)
        try:
            return int(float(num_part) * 1000)
        except ValueError:
            return None
    else:
        num_part = re.sub(r'[^\d]', '', s)
        try:
            return int(num_part)
        except ValueError:
            return None

UNUSABLE_NAMES = {'#name?', 'women', 'girls', 'men', 'boys', 'cotton'}

def is_usable_name(name):
    if not name:
        return False
    n = name.strip()
    if len(n) < 3:
        return False
    if n.startswith('#'):
        return False
    if n.lower() in UNUSABLE_NAMES:
        return False
    return True

def generate_product_id(gender, brand, name):
    canonical_str = f"{gender.strip()}:{brand.strip().lower()}:{name.strip().lower()}"
    h = hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()[:16]
    return f"prod_{h}"

def build_catalog():
    datasets = [
        ('Kids', 'data/catalog/raw/Kids.xlsx'),
        ('Women', 'data/catalog/raw/WOMEN.xlsx'),
        ('Men', 'data/catalog/raw/myntra-MEN.xlsx')
    ]
    
    source_stats = {}
    cleaned_products = []
    
    total_source_rows = 0
    total_usable_rows = 0
    total_unusable_rows = 0
    total_duplicates_removed = 0
    
    for gender, path in datasets:
        print(f"\nProcessing {gender} from {path}...")
        raw_rows = parse_full_xlsx(path)
        src_count = len(raw_rows)
        total_source_rows += src_count
        
        usable_rows = []
        unusable_count = 0
        for r in raw_rows:
            p_name = r.get('Product Name')
            if is_usable_name(p_name):
                usable_rows.append(r)
            else:
                unusable_count += 1
                
        total_usable_rows += len(usable_rows)
        total_unusable_rows += unusable_count
        
        # Deduplication per (gender, brand.lower(), name.lower())
        grouped = defaultdict(list)
        for r in usable_rows:
            brand = (r.get('Product Brand') or '').strip()
            name = (r.get('Product Name') or '').strip()
            key = (gender, brand.lower(), name.lower())
            grouped[key].append(r)
            
        dupes_in_dataset = len(usable_rows) - len(grouped)
        total_duplicates_removed += dupes_in_dataset
        
        source_stats[gender] = {
            'source_rows': src_count,
            'usable_rows': len(usable_rows),
            'unusable_rows': unusable_count,
            'unique_products': len(grouped),
            'duplicates_removed': dupes_in_dataset
        }
        
        print(f"  {gender} Stats: Source={src_count}, Usable={len(usable_rows)}, Unusable={unusable_count}, Unique={len(grouped)}, Dupes={dupes_in_dataset}")
        
        # Select best representative record per product
        for (g, b_low, n_low), items in grouped.items():
            # Scoring function for choosing the best snapshot:
            # 1. Has valid parsed price (+1000)
            # 2. Number of verified buyers (normalized log or raw count)
            # 3. Has rating (+100)
            # 4. Rating value
            # 5. Has discount (+10)
            def record_score(item):
                p = parse_price(item.get('Product Price'))
                vb = parse_buyers(item.get('Verified Buyers')) or 0
                r = parse_rating(item.get('Product Rating'))
                d = parse_discount(item.get('Discount'), p)
                score = 0
                if p is not None:
                    score += 1000000
                score += min(vb, 100000)
                if r is not None:
                    score += 1000 + int(r * 10)
                if d is not None:
                    score += 100
                return score
            
            best_item = max(items, key=record_score)
            
            # Format canonical fields
            raw_brand = (best_item.get('Product Brand') or '').strip()
            raw_name = (best_item.get('Product Name') or '').strip()
            price_val = parse_price(best_item.get('Product Price'))
            discount_val = parse_discount(best_item.get('Discount'), price_val)
            rating_val = parse_rating(best_item.get('Product Rating'))
            buyers_val = parse_buyers(best_item.get('Verified Buyers'))
            category_val = extract_category(raw_name)
            pid = generate_product_id(g, raw_brand, raw_name)
            
            prod_record = {
                'product_id': pid,
                'name': raw_name,
                'brand': raw_brand,
                'gender': g,
                'category': category_val,
                'price': price_val,
                'price_inr': price_val,
                'discount': discount_val,
                'discount_percent': discount_val,
                'rating': rating_val,
                'verified_buyers': buyers_val
            }
            cleaned_products.append(prod_record)

    print(f"\nTotal Cleaned Products: {len(cleaned_products)}")
    
    # Save CSV
    out_csv = 'data/catalog/cleaned_clothing_catalog.csv'
    fieldnames = ['product_id', 'name', 'brand', 'gender', 'category', 'price', 'price_inr', 'discount', 'discount_percent', 'rating', 'verified_buyers']
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in cleaned_products:
            writer.writerow(p)
    print(f"Saved CSV to {out_csv} ({os.path.getsize(out_csv):,} bytes)")
    
    # Save JSON
    out_json = 'data/catalog/cleaned_clothing_catalog.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(cleaned_products, f, indent=2)
    print(f"Saved JSON to {out_json} ({os.path.getsize(out_json):,} bytes)")
    
    # Profiling Calculations
    total_cleaned = len(cleaned_products)
    
    missing_counts = {
        'price_inr': sum(1 for p in cleaned_products if p['price_inr'] is None),
        'discount_percent': sum(1 for p in cleaned_products if p['discount_percent'] is None),
        'rating': sum(1 for p in cleaned_products if p['rating'] is None),
        'verified_buyers': sum(1 for p in cleaned_products if p['verified_buyers'] is None)
    }
    
    category_dist = Counter(p['category'] for p in cleaned_products)
    gender_dist = Counter(p['gender'] for p in cleaned_products)
    
    valid_prices = [p['price_inr'] for p in cleaned_products if p['price_inr'] is not None]
    price_stats = {
        'count': len(valid_prices),
        'min': min(valid_prices) if valid_prices else 0,
        'max': max(valid_prices) if valid_prices else 0,
        'mean': round(sum(valid_prices)/len(valid_prices), 2) if valid_prices else 0,
        'median': sorted(valid_prices)[len(valid_prices)//2] if valid_prices else 0
    }
    
    unique_brands = set(p['brand'] for p in cleaned_products)
    top_brands = Counter(p['brand'] for p in cleaned_products).most_common(20)
    
    valid_ratings = [p['rating'] for p in cleaned_products if p['rating'] is not None]
    rating_buckets = {
        '4.5 - 5.0': sum(1 for r in valid_ratings if 4.5 <= r <= 5.0),
        '4.0 - 4.4': sum(1 for r in valid_ratings if 4.0 <= r < 4.5),
        '3.5 - 3.9': sum(1 for r in valid_ratings if 3.5 <= r < 4.0),
        '3.0 - 3.4': sum(1 for r in valid_ratings if 3.0 <= r < 3.5),
        'Below 3.0': sum(1 for r in valid_ratings if r < 3.0),
    }
    
    profiling_summary = {
        'source_stats': source_stats,
        'total_source_rows': total_source_rows,
        'total_usable_rows': total_usable_rows,
        'total_unusable_rows': total_unusable_rows,
        'total_cleaned': total_cleaned,
        'total_duplicates_removed': total_duplicates_removed,
        'missing_counts': missing_counts,
        'category_dist': dict(category_dist.most_common()),
        'gender_dist': dict(gender_dist),
        'price_stats': price_stats,
        'brand_count': len(unique_brands),
        'top_brands': top_brands,
        'rating_stats': {
            'count': len(valid_ratings),
            'mean': round(sum(valid_ratings)/len(valid_ratings), 2) if valid_ratings else 0,
            'buckets': rating_buckets
        },
        'schema': [
            {'field': 'product_id', 'type': 'string', 'nullable': False, 'description': 'Deterministic SHA-256 identifier (prod_...)'},
            {'field': 'name', 'type': 'string', 'nullable': False, 'description': 'Cleaned product name'},
            {'field': 'brand', 'type': 'string', 'nullable': False, 'description': 'Manufacturer / Brand label'},
            {'field': 'gender', 'type': 'string', 'nullable': False, 'description': 'Target gender segment (Men, Women, Kids)'},
            {'field': 'category', 'type': 'string', 'nullable': False, 'description': 'Inferred apparel category taxonomy'},
            {'field': 'price_inr', 'type': 'float', 'nullable': True, 'description': 'Selling price in Indian Rupees (INR)'},
            {'field': 'discount_percent', 'type': 'float', 'nullable': True, 'description': 'Discount percentage (0-100)'},
            {'field': 'rating', 'type': 'float', 'nullable': True, 'description': 'Product average customer rating (1.0 - 5.0)'},
            {'field': 'verified_buyers', 'type': 'integer', 'nullable': True, 'description': 'Count of verified purchasers who reviewed'}
        ]
    }
    
    with open('data/catalog/profiling_summary.json', 'w', encoding='utf-8') as f:
        json.dump(profiling_summary, f, indent=2)
    print("Saved profiling summary to data/catalog/profiling_summary.json")

if __name__ == '__main__':
    build_catalog()
