# Electronics storefront

20 November 2026. ProductStat uses an electronics-focused catalogue and a teal, navy and white storefront based on the supplied visual reference. Products and specifications are fictional demo records; artwork is original SVG, without manufacturer endorsements, fabricated reviews or advertised discounts.

## Visible catalogue

The curated local store has 14 products and 42 Black/Silver/Blue SKUs in seven categories: Laptops & PCs, Mobile & Tablets, Audio, Cameras, Smart Home, Tools & Gadgets, and Accessories. SKU attributes contain `color`, `color_hex`, `image_url` and a specification. Product details and cart thumbnails use the selected SKU image. Generic imported products can fall back to their product image when no variant image is supplied.

Previous products are archived by publication status. Their identities, SKU stock/reservations, order snapshots, payments, settlements, returns and refunds remain available to operations and historical reporting. Archived products cannot be added to carts; existing carts remove archived lines while retaining active items.

The first migration of the preserved demo database verified all original transaction records and original SKU prices, stock and reservations were unchanged. A second application created no duplicate products, SKUs or stock movements. Sanitized counts and outcomes are in [electronics-curation.json](evidence/electronics-curation.json).

## Apply to an existing local demo

From Ubuntu WSL:

```bash
cd /mnt/d/Shadman-Desktop/Career/productstat
source scripts/env.sh
cd backend
python manage.py curate_electronics                         # preview, no writes
python manage.py curate_electronics --apply --actor administrator
```

Apply deliberately: this archives every currently published product outside the curated product IDs. It never deletes products or transaction records, resets existing stock, or rewrites historical product names. Missing curated products/SKUs receive synthetic opening stock with audited movements. Existing curated prices and stock are retained on subsequent runs.

`seed_demo` uses these electronics families for fresh databases while retaining its requested SKU/order scale. Do not reset a preserved database to change the storefront.

## Interface

- A 17.5px root and rem-based text replace the original 14px baseline, giving approximately 125% typography at normal browser zoom. Responsive layouts reflow instead of applying CSS zoom.
- The header uses a shopping-cart brand mark, a functional store search, category navigation and a cart icon. Its circular badge shows total units, hides when empty and displays `99+` for larger carts; the accessible name includes the exact quantity.
- Colour buttons expose their selected state and update the image, alt text, price and available quantity. Quantity is clamped to the chosen variant's available stock.
- Storefront copy uses “Add to cart” and “Your shopping cart”, with English/Bangla support.
- All 43 SVGs can be regenerated with `python3 scripts/generate-electronics-art.py`; no external image service is required at runtime.

## Staff image editing and homepage refinement

The staff product drawer provides all 42 electronics library images and an editable public image URL with a preview. It preserves existing custom/legacy references on opening. Each variant exposes its colour name, hex value and independent image, plus **Use product image** to clear the override. Library selection fills the matching colour; a generic colour label follows the change while customized labels are retained. Unrelated attributes, specifications, prices and stock remain intact.

Image controls support existing public assets and hosted HTTPS images. They do not upload files or promise that a third-party URL will remain available. Failed previews show a useful error and retry action. Backend validation applies to product and variant image references and rejects unsafe schemes, path traversal, control characters and malformed colour values.

The homepage uses a shorter hero, functional laptop/category links, compact catalogue controls and a product spotlight. Spotlight price, stock state and product link come from the catalogue API independently of current search filters; an unavailable response shows an explicit unavailable state with no fabricated price.

The full automated purchase, fulfilment, partial-return, refund and analytics journey remains part of the browser suite. Live payment execution, hosting and operational recovery limits remain as recorded in [RELEASE_STATUS.md](RELEASE_STATUS.md).
