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
    Guarantees strict schema adherence and zero null-type mismatch.
    """
    base_store_url, collection_path = normalize_store_url(raw_url)
    endpoint_base = f"{base_store_url}{collection_path}" if collection_path else base_store_url

    results: List[Dict[str, Any]] = []
    page = 1
    limit_per_page = 250
    total_store_products = 0

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
                # If page 1 failed completely, return empty list (store error logged)
                if log_fn:
                    log_fn(f"Unable to extract /products.json from {endpoint_base}.")
            break

        products = response_data.get("products", [])
        if not products:
            break

        for prod in products:
            if total_store_products >= max_products:
                break

            title = str(prod.get("title") or "")
            vendor = str(prod.get("vendor") or "")
            handle = str(prod.get("handle") or "")
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
                var_img_url = ""
                if isinstance(feat_img, dict) and feat_img.get("src"):
                    var_img_url = str(feat_img.get("src"))
                elif isinstance(feat_img, str):
                    var_img_url = feat_img

                parsed_variants.append({
                    "id": str(v.get("id") or ""),
                    "title": str(v.get("title") or ""),
                    "sku": str(v.get("sku") or ""),
                    "price": float(p_price) if p_price is not None else 0.0,
                    "compareAtPrice": float(c_price) if c_price is not None else 0.0,
                    "hasDiscount": has_var_discount,
                    "discountPercent": float(var_discount_pct),
                    "available": is_avail,
                    "requiresShipping": bool(v.get("requires_shipping", True)),
                    "taxable": bool(v.get("taxable", True)),
                    "option1": str(v.get("option1") or ""),
                    "option2": str(v.get("option2") or ""),
                    "option3": str(v.get("option3") or ""),
                    "featuredImageUrl": var_img_url
                })

            in_stock = available_variants_count > 0

            # Stock filter check
            if only_in_stock and not in_stock:
                continue

            # Pricing aggregates (strictly float)
            min_price = float(min(prices)) if prices else 0.0
            max_price = float(max(prices)) if prices else 0.0
            highest_compare = float(max(compare_prices)) if compare_prices else 0.0
            has_discount = bool(highest_compare > min_price and highest_compare > 0)
            discount_percent = float(round(((highest_compare - min_price) / highest_compare) * 100, 1)) if (has_discount and highest_compare > 0) else 0.0

            # Images
            raw_images = prod.get("images", [])
            image_urls = [str(img.get("src")) for img in raw_images if isinstance(img, dict) and img.get("src")]
            primary_image = image_urls[0] if image_urls else ""

            # Clean description
            clean_desc = clean_html_description(prod.get("body_html"))

            # Options
            options = []
            for opt in prod.get("options", []):
                if isinstance(opt, dict):
                    options.append({
                        "name": str(opt.get("name") or ""),
                        "values": [str(val) for val in opt.get("values", [])]
                    })

            product_url = f"{base_store_url}/products/{handle}" if handle else base_store_url
            scraped_time = datetime.now(timezone.utc).isoformat()
            published_str = str(prod.get("published_at") or "")
            created_str = str(prod.get("created_at") or "")
            updated_str = str(prod.get("updated_at") or "")

            results.append({
                "storeUrl": base_store_url,
                "productId": str(prod.get("id") or ""),
                "title": title,
                "handle": handle,
                "productUrl": product_url,
                "vendor": vendor,
                "productType": str(prod.get("product_type") or ""),
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
                "publishedAt": published_str,
                "createdAt": created_str,
                "updatedAt": updated_str,
                "scrapedAt": scraped_time
            })
            total_store_products += 1

        page += 1
        await asyncio.sleep(0.2)

    return results
