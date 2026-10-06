import re
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup


def normalize_store_url(input_url: str) -> Tuple[str, Optional[str]]:
    """
    Normalizes input URL to extract base store URL and optional collection path.
    Returns: (base_store_url, collection_endpoint_prefix or None)
    """
    clean_url = input_url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url

    parsed = urlparse(clean_url)
    scheme = parsed.scheme if parsed.scheme in ["http", "https"] else "https"
    netloc = parsed.netloc

    # Remove default port if standard
    if netloc.endswith(":443"):
        netloc = netloc[:-4]
    elif netloc.endswith(":80"):
        netloc = netloc[:-3]

    base_url = f"{scheme}://{netloc}"
    path = parsed.path.rstrip("/")

    # Check if a specific collection was requested (e.g. /collections/mens-shoes)
    collection_match = re.match(r"^(/collections/[^/]+)", path)
    if collection_match:
        collection_path = collection_match.group(1)
        return base_url, collection_path

    return base_url, None


def clean_html_description(html_text: Optional[str]) -> str:
    """Safely extracts clean plain text from HTML description."""
    if not html_text:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)
    except Exception:
        # Fallback regex tag stripping
        clean = re.sub(r"<[^>]+>", " ", html_text)
        return re.sub(r"\s+", " ", clean).strip()


def parse_float_safe(val: Any) -> Optional[float]:
    """Safely converts price strings to floats."""
    if val is None:
        return None
    try:
        f = float(str(val).replace(",", "").strip())
        return round(f, 2)
    except (ValueError, TypeError):
        return None


def parse_date_safe(val: Any) -> Optional[datetime]:
    """Safely parses ISO date string."""
    if not val:
        return None
    try:
        # Normalize trailing Z
        val_str = str(val).replace("Z", "+00:00")
        return datetime.fromisoformat(val_str)
    except Exception:
        return None


async def scrape_shopify_store(
    client: httpx.AsyncClient,
    raw_url: str,
    max_products: int = 100,
    only_in_stock: bool = False,
    search_keyword: str = "",
    published_after: str = "",
    flatten_variants: bool = False,
    log_fn: Any = None
) -> List[Dict[str, Any]]:
    """
    Scrapes products from a Shopify store or collection using public /products.json.
    Handles pagination, filtering, variants, and resilient error recovery.
    """
    base_store_url, collection_path = normalize_store_url(raw_url)
    endpoint_base = f"{base_store_url}{collection_path}" if collection_path else base_store_url

    results: List[Dict[str, Any]] = []
    page = 1
    limit_per_page = 250
    total_store_products = 0

    # Parse published_after filter if provided
    filter_date = None
    if published_after:
        filter_date = parse_date_safe(published_after)

    keyword_clean = search_keyword.strip().lower() if search_keyword else None

    if log_fn:
        log_fn(f"Targeting store: {endpoint_base} (max products: {max_products})")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }

    while total_store_products < max_products:
        fetch_limit = min(limit_per_page, max_products - total_store_products)
        products_url = f"{endpoint_base}/products.json?limit={fetch_limit}&page={page}"

        response_data = None
        for attempt in range(3):
            try:
                resp = await client.get(products_url, headers=headers)
                if resp.status_code == 200:
                    try:
                        response_data = resp.json()
                        break
                    except Exception:
                        if log_fn:
                            log_fn(f"Invalid JSON returned from {products_url}")
                        break
                elif resp.status_code in [404, 403, 401]:
                    if log_fn:
                        log_fn(f"Store endpoint returned HTTP {resp.status_code}: {products_url}")
                    break
                elif resp.status_code == 429:
                    wait_time = (attempt + 1) * 2
                    if log_fn:
                        log_fn(f"Rate limited (429) on {endpoint_base}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(1.0)
            except Exception as e:
                if attempt == 2 and log_fn:
                    log_fn(f"Failed to fetch {products_url}: {e}")
                await asyncio.sleep(1.0)

        if not response_data or "products" not in response_data:
            if page == 1:
                # If page 1 failed completely, yield diagnostic record
                return [{
                    "storeUrl": base_store_url,
                    "targetUrl": raw_url,
                    "isShopify": False,
                    "error": "Unable to extract /products.json. Store may be password-protected or not running on Shopify.",
                    "productsCount": 0,
                    "scrapedAt": datetime.now(timezone.utc).isoformat()
                }]
            break

        products = response_data.get("products", [])
        if not products:
            # End of pagination
            break

        for prod in products:
            if total_store_products >= max_products:
                break

            title = prod.get("title", "")
            vendor = prod.get("vendor", "")
            handle = prod.get("handle", "")
            tags_raw = prod.get("tags", [])
            tags = tags_raw if isinstance(tags_raw, list) else [t.strip() for t in str(tags_raw).split(",") if t.strip()]

            # Keyword filter check
            if keyword_clean:
                searchable_text = f"{title} {vendor} {' '.join(tags)}".lower()
                if keyword_clean not in searchable_text:
                    continue

            # Date filter check
            published_at_str = prod.get("published_at")
            if filter_date and published_at_str:
                prod_pub_date = parse_date_safe(published_at_str)
                if prod_pub_date and prod_pub_date < filter_date:
                    continue

            # Process variants
            raw_variants = prod.get("variants", [])
            parsed_variants = []
            prices = []
            compare_prices = []
            available_variants_count = 0

            for v in raw_variants:
                p_price = parse_float_safe(v.get("price"))
                c_price = parse_float_safe(v.get("compare_at_price"))
                is_avail = bool(v.get("available", False))

                if p_price is not None:
                    prices.append(p_price)
                if c_price is not None:
                    compare_prices.append(c_price)
                if is_avail:
                    available_variants_count += 1

                has_var_discount = (c_price is not None and p_price is not None and c_price > p_price)
                var_discount_pct = round(((c_price - p_price) / c_price) * 100, 1) if (has_var_discount and c_price > 0) else 0.0

                feat_img = v.get("featured_image")
                var_img_url = feat_img.get("src") if isinstance(feat_img, dict) else (feat_img if isinstance(feat_img, str) else None)

                parsed_variants.append({
                    "id": str(v.get("id")),
                    "title": v.get("title"),
                    "sku": v.get("sku") or "",
                    "price": p_price,
                    "compareAtPrice": c_price,
                    "hasDiscount": has_var_discount,
                    "discountPercent": var_discount_pct,
                    "available": is_avail,
                    "requiresShipping": v.get("requires_shipping", True),
                    "taxable": v.get("taxable", True),
                    "option1": v.get("option1"),
                    "option2": v.get("option2"),
                    "option3": v.get("option3"),
                    "featuredImageUrl": var_img_url
                })

            in_stock = available_variants_count > 0

            # Stock filter check
            if only_in_stock and not in_stock:
                continue

            # Pricing aggregates
            min_price = min(prices) if prices else None
            max_price = max(prices) if prices else None
            highest_compare = max(compare_prices) if compare_prices else None
            has_discount = bool(highest_compare and min_price and highest_compare > min_price)
            discount_percent = round(((highest_compare - min_price) / highest_compare) * 100, 1) if (has_discount and highest_compare > 0) else 0.0

            # Images
            raw_images = prod.get("images", [])
            image_urls = [img.get("src") for img in raw_images if isinstance(img, dict) and img.get("src")]
            primary_image = image_urls[0] if image_urls else None

            # Clean description
            clean_desc = clean_html_description(prod.get("body_html"))

            # Clean options
            options = []
            for opt in prod.get("options", []):
                if isinstance(opt, dict):
                    options.append({
                        "name": opt.get("name"),
                        "values": opt.get("values", [])
                    })

            product_url = f"{base_store_url}/products/{handle}" if handle else base_store_url
            scraped_time = datetime.now(timezone.utc).isoformat()

            if flatten_variants:
                # Yield one row per variant
                for pv in parsed_variants:
                    results.append({
                        "storeUrl": base_store_url,
                        "productId": str(prod.get("id")),
                        "title": title,
                        "handle": handle,
                        "productUrl": product_url,
                        "vendor": vendor,
                        "productType": prod.get("product_type", ""),
                        "tags": tags,
                        "variantId": pv["id"],
                        "variantTitle": pv["title"],
                        "sku": pv["sku"],
                        "price": pv["price"],
                        "compareAtPrice": pv["compareAtPrice"],
                        "hasDiscount": pv["hasDiscount"],
                        "discountPercent": pv["discountPercent"],
                        "inStock": pv["available"],
                        "option1": pv["option1"],
                        "option2": pv["option2"],
                        "option3": pv["option3"],
                        "primaryImageUrl": pv["featuredImageUrl"] or primary_image,
                        "publishedAt": prod.get("published_at"),
                        "createdAt": prod.get("created_at"),
                        "updatedAt": prod.get("updated_at"),
                        "scrapedAt": scraped_time
                    })
                    total_store_products += 1
                    if total_store_products >= max_products:
                        break
            else:
                # Yield one row per product
                results.append({
                    "storeUrl": base_store_url,
                    "productId": str(prod.get("id")),
                    "title": title,
                    "handle": handle,
                    "productUrl": product_url,
                    "vendor": vendor,
                    "productType": prod.get("product_type", ""),
                    "tags": tags,
                    "description": clean_desc[:1000] if clean_desc else "",
                    "minPrice": min_price,
                    "maxPrice": max_price,
                    "compareAtPrice": highest_compare,
                    "hasDiscount": has_discount,
                    "discountPercent": discount_percent,
                    "inStock": in_stock,
                    "totalVariants": len(parsed_variants),
                    "availableVariants": available_variants_count,
                    "primaryImageUrl": primary_image,
                    "imageUrls": image_urls,
                    "options": options,
                    "variants": parsed_variants,
                    "publishedAt": prod.get("published_at"),
                    "createdAt": prod.get("created_at"),
                    "updatedAt": prod.get("updated_at"),
                    "scrapedAt": scraped_time
                })
                total_store_products += 1

        page += 1
        # Gentle pacing between store pages
        await asyncio.sleep(0.2)

    return results
