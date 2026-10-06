import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any
import httpx
from apify import Actor
from src.shopify_scraper import scrape_shopify_store


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get("startUrls", [])
        max_products_per_store = int(actor_input.get("maxProductsPerStore", 100))
        only_in_stock = bool(actor_input.get("onlyInStock", False))
        search_keyword = str(actor_input.get("searchKeyword", "")).strip()
        published_after = str(actor_input.get("publishedAfter", "")).strip()
        flatten_variants = bool(actor_input.get("flattenVariants", False))

        # Default fallback if empty
        if not start_urls:
            start_urls = [{"url": "https://allbirds.com"}]

        Actor.log.info("=" * 60)
        Actor.log.info("🛍️ Starting Shopify Store & Product Catalog Spy")
        Actor.log.info(f"Target stores count: {len(start_urls)}")
        Actor.log.info(f"Max products per store: {max_products_per_store}")
        Actor.log.info(f"Only in stock: {only_in_stock}")
        if search_keyword:
            Actor.log.info(f"Keyword filter: '{search_keyword}'")
        if published_after:
            Actor.log.info(f"Published after: '{published_after}'")
        Actor.log.info("=" * 60)

        total_extracted_records = 0
        successful_stores = 0

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            for item in start_urls:
                raw_url = item.get("url") if isinstance(item, dict) else str(item)
                if not raw_url or not raw_url.strip():
                    continue

                raw_url = raw_url.strip()
                Actor.log.info(f"Processing store: {raw_url}")

                try:
                    records = await scrape_shopify_store(
                        client=client,
                        raw_url=raw_url,
                        max_products=max_products_per_store,
                        only_in_stock=only_in_stock,
                        search_keyword=search_keyword,
                        published_after=published_after,
                        flatten_variants=flatten_variants,
                        log_fn=Actor.log.info
                    )

                    if records:
                        successful_stores += 1
                        # Push records in safe batches
                        batch_size = 50
                        for i in range(0, len(records), batch_size):
                            chunk = records[i:i + batch_size]
                            try:
                                await Actor.push_data(chunk)
                            except Exception as push_err:
                                Actor.log.error(f"Failed to push batch to dataset: {push_err}")
                                if hasattr(push_err, "data"):
                                    Actor.log.error(f"Push error details: {push_err.data}")
                                raise push_err

                        total_extracted_records += len(records)
                        Actor.log.info(f"Saved {len(records)} products for store: {raw_url}")
                    else:
                        Actor.log.warning(f"No products matched the given criteria for: {raw_url}")

                except Exception as e:
                    Actor.log.error(f"Error processing store {raw_url}: {e}", exc_info=True)

        Actor.log.info("=" * 60)
        Actor.log.info(f"🎉 Run completed successfully!")
        Actor.log.info(f"Total stores processed: {len(start_urls)} ({successful_stores} active Shopify stores)")
        Actor.log.info(f"Total records pushed to dataset: {total_extracted_records}")
        Actor.log.info("=" * 60)
