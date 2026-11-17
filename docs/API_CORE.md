# Core API contract

Base `/api/v1/`. Cookie sessions, same origin. `GET bootstrap/` obtains the CSRF token; all unsafe requests, including guest cart/checkout/login, send `X-CSRFToken` and cookies. Bootstrap/login/register/logout responses include the current `csrfToken`. Roles: `administrator`, `operator`, `analyst`, `customer`. Catalog/inventory readers: first three. Customer operations and commerce writes: administrator/operator. Analysts receive redacted analytics without customer-order access. User/settings/refund confirmation: administrator.

Money is serialized as decimal strings; UUIDs are strings. Errors are HTTP 400/403/404/409/503 with `detail` or field validation errors. All order access requires its owning logged-in customer or `?token=<access_token>` (alternatively `X-Order-Token`). Staff detail uses the staff route. Historical records are read-only.

`GET bootstrap/` returns `{user:null|{id,username,email,role,is_active},company:{name,support_email,currency,timezone,return_window_days,cod_enabled,logo_url},csrfToken,delivery_zones:[{id,name,charge}],payment:{cod,sslcommerz_enabled,sandbox},demo}`.

`POST auth/register/`: `{username,email,password}`. `POST auth/login/`: `{username,password}`. `POST auth/logout/`: `{}`. All return `{user,csrfToken}`.

`GET catalog/products/?q=&category=&sort=newest|name|price_asc|price_desc&page=1&page_size=24` returns `{count,page,page_size,categories:[string],results:[product]}`. `GET catalog/products/<slug>/` returns one product. Product shape: `{id,name,slug,description,category,image_url,is_active,created_at,skus:[{id,code,label,attributes,price,available,is_active}],min_price,total_available}`. Product images may be `/products/bag.svg` etc.

`GET cart/` returns `{items:[{sku_id,quantity,sku:{id,code,label,attributes,price,available,is_active},product:{name,slug,image_url},line_total}],subtotal}`. `POST cart/ {sku_id,quantity}` sets quantity (zero removes). `DELETE cart/` clears.

`POST checkout/`, header `Idempotency-Key: <new UUID per checkout attempt>`:

```json
{"customer_name":"Demo Customer","email":"","phone":"01712345678","address":{"line1":"21 Example Road","area":"Panchlaish","city":"Chattogram","postal_code":"4203"},"delivery_zone_id":1,"payment_method":"cod"}
```

Uses session cart. Response `{order,access_token,payment_url:null|string}`. Retry the same payload and key after a network error. The key is bound to the persisted client session and authenticated user. Empty-cart retries replay the original result. Reusing a key with a changed nonempty cart returns 400 and preserves that cart; use a new key for a new purchase. Online payments return 503 when credentials are not configured. A gateway initiation failure leaves a pending reserved order; retry with the same key or allow expiry. A returned gateway URL is the provider page, not a simulated success.

`GET orders/` returns `{results:[order]}` for the logged-in customer. `GET orders/<uuid>/?token=` returns order. `POST orders/<uuid>/cancel/?token= {}` cancels all undispatched merchandise; optional `{lines:[{order_line_id,quantity}]}` cancels a subset of confirmed COD/paid orders. `POST orders/<uuid>/returns/?token= {reason,lines:[{order_line_id,quantity}]}` requests a return.

Order fields: `{id,number,status,payment_method,customer_name,email,phone,address,subtotal,discount_total,shipping_total,tax_total,grand_total,collected_total,refunded_total,created_at,confirmed_at,dispatched_at,delivered_at,reservation_expires_at,is_historical,source,lines,shipments,payments,returns,refunds}`.

Order line: `{id,sku_id,sku_code,product_name,variant_name,quantity,cancelled_quantity,shipped_quantity,delivered_quantity,returned_quantity,unit_price,discount_total,line_total}`. Shipment: `{id,state,carrier,tracking_number,dispatched_at,delivered_at}`. Payment: `{id,method,status,amount,settled_amount,collected_at,settled_at}`. Order statuses: `pending_payment`, `confirmed`, `dispatched`, `delivered`, `failed`, `returned_to_origin`, `cancelled`.

`GET staff/orders/?q=&status=&source=live` returns `{count,results:[order]}` (latest 100). `GET staff/orders/<uuid>/` returns full order. `POST staff/orders/<uuid>/action/`:

- `{action:"dispatch",carrier,tracking_number}`
- `{action:"deliver"}` / `{action:"fail"}` / `{action:"return_to_origin"}`
- `{action:"cancel",lines?:[{order_line_id,quantity}]}`
- `{action:"collect_cod",amount:"1090.00",reference:"Courier receipt"}`
- `{action:"settle_cod",amount:"1090.00",reference:"Bank receipt"}`

`GET staff/returns/?status=` returns `{results:[return]}`. Return: `{id,order_id,order_number,status,reason,created_at,received_at,inspected_at,lines:[{id,order_line_id,product_name,quantity,accepted_quantity,restock_quantity,disposition}]}`.

`POST staff/returns/<uuid>/action/` accepts `{action:"approve"|"reject"|"receive"}` or `{action:"inspect",lines:[{id:<return_line_id>,accepted_quantity:1,restock_quantity:1,disposition:"restock"}]}`. Inspect every line exactly once. Disposition is `restock`, `quarantine`, or `dispose`. Only `restock_quantity` increases stock. Accepted merchandise creates a refund obligation only against money actually collected; uncollected COD returns reduce the amount due.

`GET staff/refunds/` returns `{results:[{id,order_id,order_number,amount,status,reason,reference,created_at,confirmed_at}]}`. `POST staff/refunds/<uuid>/confirm/ {reference}` records an independently completed refund, restricted to administrators. It does not execute a gateway refund.

`GET staff/products/` returns `{results:[product]}` including inactive entries. `POST staff/products/ {name,slug,category,description,image_url,is_active,skus:[{code,label,attributes,price,is_active}]}` creates product/SKUs. `PATCH staff/products/<uuid>/` updates fields. SKU updates include `id`; new SKU entries omit it. Stock cannot be written here.

`GET staff/inventory/?q=` returns `{results:[{id,code,label,product_name,on_hand,reserved,available,price}]}`. `POST staff/inventory/ {sku_id,delta:5,reason:"Opening stock"}` records a signed stock adjustment. Cannot reduce on-hand below reservations.

`GET staff/users/` returns `{results:[{id,username,email,first_name,last_name,role,is_active}]}`. `POST staff/users/` accepts these fields plus password; `PATCH staff/users/<id>/` edits them. Current administrator cannot remove their own access.

`GET/PATCH staff/settings/` uses company fields plus `delivery_zones:[{id?,name,charge,is_active}]`. Currency and timezone are fixed to BDT/Asia-Dhaka. `GET staff/audit/` returns latest 200 staff audit events.

`GET health/` probes DB and Redis with a one-second network timeout; returns 503 without internal connection details on failure. Health is exempt from HTTPS redirect for internal container probes. Payment callback endpoints `POST payments/sslcommerz/ipn/` and `GET/POST payments/sslcommerz/return/` are CSRF-exempt provider entry points. Neither trusts posted success: server validation checks provider, transaction ID, amount and BDT currency. Late payments produce reconciliation exceptions and refund obligations without reopening expired inventory allocations.

## Preparation, tax and environment boundaries

Orders expose `amount_due` as the remaining customer collection after cancelled/accepted-return allocations and confirmed receipts (zero for cancelled/failed/returned-to-origin orders), and `settled_total` as recorded courier settlements. Original `grand_total`, confirmed `collected_total` and confirmed `refunded_total` remain separate snapshots/balances. Settlement is not subtracted again from the customer's amount due.

Return eligibility ends at the end of the configured calendar day in `Asia/Dhaka`: a delivery on 1 November with a seven-day window accepts requests through 8 November, including that evening, and closes at midnight on 9 November. This is independent of refund completion.

`POST staff/orders/<uuid>/action/ {action:"prepare"}` moves confirmed orders to `preparing` and snapshots `prepared_at`. Dispatch accepts confirmed or preparing orders; cancellation accepts both before dispatch. Lists accept `page` and `page_size` (maximum 100) and return count/page/page_size/results.

Company `tax_rate` is an exact decimal percentage from 0 to 100, configurable through staff settings and exposed by bootstrap. Demo defaults to zero. Checkout taxes merchandise only, exclusive of shipping, and rounds each line to paisa. `OrderLine.tax_total` and `Order.tax_total` are immutable sale snapshots; changes to the current tax rate never rewrite them. `grand_total` includes tax. Partial cancellation and accepted returns allocate snapshotted tax using cumulative rounding so repeated partial actions cannot manufacture pennies. Full paid cancellation refunds shipping too. RefundLine.amount is total cash; `tax_amount` and `shipping_amount` identify its components for merchandise-only reporting.

Sandbox payment initiation is disabled outside PRODUCTSTAT_DEMO, and sandbox-flagged payments cannot authorize real-company preparation/dispatch. Payment responses expose `is_sandbox`. Demo notifications are suppressed even if SMTP credentials exist. Every API response carries `X-Request-ID`; structured request logs omit query strings, payloads and customer data.
