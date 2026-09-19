"""Synthetic E-Commerce Customer Behavioral Dataset Generator.

Generates generic customer-level behavioral observations mapped to Task 9's
canonical `customer_features` vocabulary for ML lead-scoring model training.

DO NOT use domain-specific product names, clothing categories, or brand strings.
"""

import os
import numpy as np
import pandas as pd


def generate_ecommerce_dataset(num_samples=6000, seed=42):
    np.random.seed(seed)

    customer_ids = [f"cust_{i+1:04d}" for i in range(num_samples)]

    # 1. Engagement Features
    sessions_count = np.random.negative_binomial(n=2, p=0.3, size=num_samples) + 1
    events_per_session = np.random.uniform(4, 15, size=num_samples)
    total_events = (sessions_count * events_per_session).astype(int)

    session_duration_avg = np.random.gamma(shape=2.5, scale=60, size=num_samples) + 15
    total_time_spent = sessions_count * session_duration_avg
    average_session_duration = total_time_spent / sessions_count

    page_views_count = (total_events * np.random.uniform(0.4, 0.7, size=num_samples)).astype(int)
    days_since_last_activity = np.round(np.random.exponential(scale=10, size=num_samples), 2)
    days_since_last_activity = np.clip(days_since_last_activity, 0.01, 90.0)

    # 2. Product Behavior
    products_viewed = (page_views_count * np.random.uniform(0.2, 0.6, size=num_samples)).astype(int)
    unique_products_viewed = np.zeros(num_samples, dtype=int)
    for i in range(num_samples):
        if products_viewed[i] > 0:
            unique_products_viewed[i] = np.random.randint(1, min(products_viewed[i] + 1, 20))
        else:
            unique_products_viewed[i] = 0

    product_interactions = products_viewed + np.random.randint(0, 5, size=num_samples)
    search_count = np.random.poisson(lam=1.2, size=num_samples)
    form_submit_count = np.random.poisson(lam=0.2, size=num_samples)
    high_intent_page_visits = np.random.poisson(lam=0.7, size=num_samples)

    # 3. Shopping Intent (Cart & Wishlist)
    cart_item_count = np.random.poisson(lam=1.5, size=num_samples)
    item_prices = np.random.gamma(shape=3.0, scale=35.0, size=num_samples)
    cart_value = np.round(cart_item_count * item_prices, 2)

    wishlist_item_count = np.random.poisson(lam=0.9, size=num_samples)

    checkout_attempts = np.zeros(num_samples, dtype=int)
    for i in range(num_samples):
        if cart_item_count[i] > 0:
            checkout_attempts[i] = np.random.choice([0, 1, 2, 3], p=[0.4, 0.4, 0.15, 0.05])

    # 4. Historical Commerce
    orders_count = np.random.poisson(lam=0.5, size=num_samples)
    order_prices = np.random.gamma(shape=4.0, scale=40.0, size=num_samples)
    total_order_value = np.round(orders_count * order_prices, 2)
    safe_orders = np.maximum(orders_count, 1)
    average_order_value = np.where(orders_count > 0, np.round(total_order_value / safe_orders, 2), 0.0)

    # 5. Derived Features
    cart_to_session_ratio = np.round(cart_item_count / sessions_count, 3)
    checkout_to_cart_ratio = np.round(checkout_attempts / np.maximum(cart_item_count, 1), 3)
    high_intent_ratio = np.round(high_intent_page_visits / np.maximum(page_views_count, 1), 3)
    product_interaction_density = np.round(product_interactions / sessions_count, 3)

    # 6. Target Label Generation (Realistic Logistic Log-Odds Function)
    # Log-odds encoded from customer intent indicators + Gaussian noise
    noise = np.random.normal(loc=0.0, scale=0.6, size=num_samples)
    log_odds = (
        -3.5
        + 1.15 * checkout_attempts
        + 0.006 * cart_value
        + 0.30 * high_intent_page_visits
        + 0.10 * product_interactions
        + 0.18 * wishlist_item_count
        - 0.045 * days_since_last_activity
        + 0.50 * orders_count
        + noise
    )

    conversion_prob = 1.0 / (1.0 + np.exp(-log_odds))
    converted_in_window = (conversion_prob >= 0.50).astype(int)

    df = pd.DataFrame({
        "customer_id": customer_ids,
        "sessions_count": sessions_count,
        "total_events": total_events,
        "total_time_spent": np.round(total_time_spent, 2),
        "average_session_duration": np.round(average_session_duration, 2),
        "page_views_count": page_views_count,
        "days_since_last_activity": days_since_last_activity,
        "products_viewed": products_viewed,
        "unique_products_viewed": unique_products_viewed,
        "product_interactions": product_interactions,
        "search_count": search_count,
        "form_submit_count": form_submit_count,
        "high_intent_page_visits": high_intent_page_visits,
        "cart_item_count": cart_item_count,
        "cart_value": cart_value,
        "wishlist_item_count": wishlist_item_count,
        "checkout_attempts": checkout_attempts,
        "orders_count": orders_count,
        "total_order_value": total_order_value,
        "average_order_value": average_order_value,
        "cart_to_session_ratio": cart_to_session_ratio,
        "checkout_to_cart_ratio": checkout_to_cart_ratio,
        "high_intent_ratio": high_intent_ratio,
        "product_interaction_density": product_interaction_density,
        "converted_in_window": converted_in_window,
    })

    return df


if __name__ == "__main__":
    out_dir = os.path.join("data", "ml")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "ecommerce_customer_behavior.csv")

    df = generate_ecommerce_dataset(num_samples=6000, seed=42)
    df.to_csv(out_path, index=False)
    print(f"Generated synthetic e-commerce dataset: {out_path}")
    print(f"Shape: {df.shape}")
    print(f"Conversion Distribution:\n{df['converted_in_window'].value_counts(normalize=True)}")
