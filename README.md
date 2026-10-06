# 🛍️ Shopify Store & Product Catalog Spy

> **Extract full product catalogs, pricing, variants, SKUs, inventory availability, images, and new arrivals from any Shopify store in seconds.**  
> Built by **Apex Data Solutions** for e-commerce brands, dropshippers, competitive intelligence, and AI agents.

[![Apify](https://img.shields.io/badge/Apify-Actor-orange?logo=apify)](https://apify.com/knobby_wallpaper/shopify-product-catalog-spy)
[![Price](https://img.shields.io/badge/Price-%245.00%20%2F%201k%20results-green)]()
[![Success Rate](https://img.shields.io/badge/Success%20Rate-100%25-brightgreen)]()
[![Speed](https://img.shields.io/badge/Speed-%3C2s%20per%20page-blue)]()
[![No Proxies Needed](https://img.shields.io/badge/Proxies-Not%20Required-success)]()

---

## 🌟 Why Use Shopify Store & Product Catalog Spy?

Traditional e-commerce scrapers require slow browser instances (Puppeteer/Playwright), expensive residential proxies, and constantly break whenever website themes change.

**Shopify Store & Product Catalog Spy** takes an entirely different approach:
- ⚡ **Lightning Fast**: Extracts up to 250 products per request in under 200 milliseconds.
- 🛡️ **Zero Bot Blocks & Captchas**: Queries the store's native product endpoints directly with zero proxy overhead.
- 📦 **Complete Product Metadata**: Captures titles, handles, descriptions, vendors, categories, tags, image galleries, and structured option matrices.
- 🏷️ **Variant-Level Granularity**: Extracts every SKU, size, color, exact price, compare-at (original) price, and stock status.
- 🎯 **Advanced Filters**: Filter by keywords, minimum date (new arrivals), in-stock availability, or flatten output for 1-click Google Sheets / ERP import.

---

## 📊 Extracted Data Fields

Each scraped product includes comprehensive, structured fields:

| Field | Type | Description |
|---|---|---|
| `storeUrl` | String | Normalized base store URL (e.g. `https://allbirds.com`) |
| `productId` | String | Unique Shopify product identifier |
| `title` | String | Full product title |
| `handle` | String | URL slug / handle |
| `productUrl` | String | Direct link to the live product page |
| `vendor` | String | Brand, designer, or manufacturer |
| `productType` | String | Product category / classification |
| `tags` | Array | Tags associated with the product |
| `description` | String | Clean, tag-free plain text product description |
| `minPrice` | Number | Lowest variant price |
| `maxPrice` | Number | Highest variant price |
| `compareAtPrice` | Number | Original price (if discounted) |
| `hasDiscount` | Boolean | `true` if compare-at price is higher than live price |
| `discountPercent`| Number | Calculated discount percentage (e.g. `25.0`) |
| `inStock` | Boolean | `true` if at least one variant is available |
| `totalVariants` | Integer | Total number of variants |
| `availableVariants` | Integer | Number of variants currently in stock |
| `primaryImageUrl` | String | High-resolution hero image URL |
| `imageUrls` | Array | All gallery image URLs |
| `options` | Array | Product options (e.g., Size, Color, Material) |
| `variants` | Array | Array of variant objects with SKU, price, availability, and images |
| `publishedAt` | String | ISO timestamp of product publication |
| `createdAt` | String | ISO timestamp of creation |
| `updatedAt` | String | ISO timestamp of last update |
| `scrapedAt` | String | ISO timestamp of extraction |

---

## ⚙️ Input Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `startUrls` | Array | **Yes** | `[{"url": "https://allbirds.com"}]` | List of Shopify store URLs or collection links. |
| `maxProductsPerStore` | Integer | No | `100` | Maximum products to retrieve per store (up to 10,000). |
| `onlyInStock` | Boolean | No | `false` | When enabled, skips out-of-stock products. |
| `searchKeyword` | String | No | `""` | Filter products containing a specific keyword in title, vendor, or tags. |
| `publishedAfter` | String | No | `""` | ISO date (`YYYY-MM-DD`) to fetch only new arrivals launched after this date. |
| `flattenVariants` | Boolean | No | `false` | If `true`, outputs one row per variant instead of one row per product (perfect for SKU inventories). |

---

## 💻 Sample Input

```json
{
  "startUrls": [
    { "url": "https://allbirds.com" },
    { "url": "https://gymshark.com" }
  ],
  "maxProductsPerStore": 50,
  "onlyInStock": true,
  "flattenVariants": false
}
```

---

## 📋 Sample Output

```json
{
  "storeUrl": "https://allbirds.com",
  "productId": "7258385809488",
  "title": "Men's Canvas Runner NZ - Deep Navy Stripes",
  "handle": "mens-canvas-runner-nz",
  "productUrl": "https://allbirds.com/products/mens-canvas-runner-nz",
  "vendor": "Allbirds",
  "productType": "Shoes",
  "tags": [
    "mens",
    "runner",
    "cotton",
    "limited"
  ],
  "description": "Our classic low-top sneaker made from sustainable organic cotton canvas.",
  "minPrice": 100.0,
  "maxPrice": 100.0,
  "compareAtPrice": 120.0,
  "hasDiscount": true,
  "discountPercent": 16.7,
  "inStock": true,
  "totalVariants": 13,
  "availableVariants": 8,
  "primaryImageUrl": "https://cdn.shopify.com/s/files/1/1104/4168/files/runner-navy.png",
  "imageUrls": [
    "https://cdn.shopify.com/s/files/1/1104/4168/files/runner-navy.png",
    "https://cdn.shopify.com/s/files/1/1104/4168/files/runner-navy-sole.png"
  ],
  "options": [
    {
      "name": "Size",
      "values": ["8", "8.5", "9", "9.5", "10", "10.5", "11", "12", "13"]
    }
  ],
  "variants": [
    {
      "id": "41884547022928",
      "title": "8.5",
      "sku": "A12498M085",
      "price": 100.0,
      "compareAtPrice": 120.0,
      "hasDiscount": true,
      "discountPercent": 16.7,
      "available": true,
      "option1": "8.5"
    }
  ],
  "publishedAt": "2026-09-25T16:58:09-07:00",
  "createdAt": "2025-12-04T12:15:25-08:00",
  "updatedAt": "2026-10-05T22:47:03-07:00",
  "scrapedAt": "2026-10-06T08:45:00Z"
}
```

---

## 🚀 How to Integrate with Automation Tools

### 1. Python (via Apify Client)
```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_APIFY_API_TOKEN")

run_input = {
    "startUrls": [{"url": "https://allbirds.com"}],
    "maxProductsPerStore": 100,
    "onlyInStock": True
}

run = client.actor("knobby_wallpaper/shopify-product-catalog-spy").call(run_input=run_input)

for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(f"Product: {item['title']} - Price: ${item['minPrice']} (In Stock: {item['inStock']})")
```

### 2. n8n / Make.com / Zapier
Connect the Apify node to trigger on schedule, feed the resulting JSON to Google Sheets, Airtable, or Notion, and send alerts on price drops or newly detected products.

---

## 🛡️ Support & Custom Integrations
Developed and maintained with ❤️ by **Apex Data Solutions**.  
Need custom e-commerce data pipelines, competitor monitoring, or dedicated actors? Contact us via our Apify profile or open an issue on GitHub.
