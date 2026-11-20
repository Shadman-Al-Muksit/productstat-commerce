import {test, expect, type APIRequestContext} from '@playwright/test';

const password = process.env.DEMO_PASSWORD || 'ProductStatDemo!2026';
const electronicsName = 'Studio Wireless Headphones';
const electronicsQuery = encodeURIComponent(electronicsName);
async function mutation(context: APIRequestContext, path: string, data: unknown) {
  const bootstrap = await (await context.get('/api/v1/bootstrap/')).json();
  const response = await context.post('/api/v1/' + path, {data, headers: {'X-CSRFToken': bootstrap.csrfToken}});
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}
async function login(context: APIRequestContext, username = 'administrator') {
  return mutation(context, 'auth/login/', {username, password});
}

test('catalogue, Bangla navigation, keyboard search and mobile layout', async ({page}) => {
  await page.goto('/?ref=walkthrough');
  await expect(page.getByTestId('product-card').first()).toBeVisible();
  await page.getByRole('button', {name: 'Switch language'}).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'bn');
  await page.getByRole('button', {name: 'Switch language'}).click();
  const search = page.getByRole('textbox', {name: 'Search products'});
  await search.fill(electronicsName);
  await expect(page.getByTestId('product-card').first()).toContainText(electronicsName);
  const headerSearch = page.getByRole('textbox', {name: 'Search entire store'});
  await headerSearch.fill('VertexBook');
  await headerSearch.press('Enter');
  await expect(search).toHaveValue('VertexBook');
  await expect(page.getByTestId('product-card').first()).toContainText('VertexBook');
  expect(new URL(page.url()).searchParams.get('q')).toBe('VertexBook');
  await search.clear();
  await expect(headerSearch).toHaveValue('');
  expect(new URL(page.url()).searchParams.has('q')).toBeFalsy();
  expect(new URL(page.url()).searchParams.get('ref')).toBe('walkthrough');
  await expect.poll(() => page.getByTestId('product-card').count()).toBeGreaterThan(1);
  await page.reload();
  await expect(search).toHaveValue('');
  await expect(headerSearch).toHaveValue('');
  await expect.poll(() => page.getByTestId('product-card').count()).toBeGreaterThan(1);
  await search.fill('VertexBook');
  await page.getByRole('region', {name: 'Shop by category'}).getByRole('button', {name: 'Audio', exact: true}).click();
  await expect(search).toHaveValue('');
  await expect(headerSearch).toHaveValue('');
  expect(new URL(page.url()).searchParams.has('q')).toBeFalsy();
  expect(new URL(page.url()).searchParams.get('category')).toBe('Audio');
  await expect(page.getByTestId('product-card').first().locator('.product-category')).toHaveText('Audio');
  await headerSearch.fill('VertexBook');
  await headerSearch.press('Enter');
  await expect(search).toHaveValue('VertexBook');
  await expect(page.getByTestId('product-card').first()).toContainText('VertexBook');
  await page.goBack();
  await expect(search).toHaveValue('');
  await expect(headerSearch).toHaveValue('');
  expect(new URL(page.url()).searchParams.get('category')).toBe('Audio');
  await expect(page.getByTestId('product-card').first().locator('.product-category')).toHaveText('Audio');
  await page.getByRole('link', {name: 'View all electronics', exact: true}).click();
  await expect.poll(() => page.getByTestId('product-card').count()).toBeGreaterThan(3);
  await page.screenshot({path: '../docs/screenshots/storefront-desktop.png', fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  await expect(page.getByTestId('product-card').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  await page.screenshot({path: '../docs/screenshots/storefront-mobile.png', fullPage: true});
});

test('electronics colours, readable text and circular cart badge work on desktop and mobile', async ({page}) => {
  await page.goto('/');
  await expect(page.getByTestId('product-card').first()).toBeVisible();
  await expect(page.getByRole('link', {name: 'Shopping cart, 0 items', exact: true})).toBeVisible();
  await expect(page.getByTestId('cart-count')).toHaveCount(0);
  expect(await page.locator('body').evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(17.5);
  expect(await page.getByRole('link', {name: 'Shop electronics', exact: true}).evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);

  const catalogue = await (await page.request.get(`/api/v1/catalog/products/?q=${electronicsQuery}&page_size=24`)).json();
  const product = catalogue.results.find((item: any) => item.skus.length >= 3 && item.skus.some((sku: any) => sku.available >= 2));
  expect(product, 'An electronics product has selectable colour variants and two available units.').toBeTruthy();
  const initialSku = product.skus.find((sku: any) => sku.available >= 2);
  await page.goto('/products/' + product.slug);
  const image = page.getByTestId('variant-product-image');
  const seenImages = new Set<string>();
  for (const sku of product.skus) {
    await page.getByRole('button', {name: sku.label, exact: true}).click();
    await expect(page.getByRole('button', {name: sku.label, exact: true})).toHaveAttribute('aria-pressed', 'true');
    await expect(image).toHaveAttribute('src', sku.attributes.image_url);
    await expect(image).toHaveAttribute('alt', `${product.name} — ${sku.label}`);
    await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBeTruthy();
    seenImages.add(sku.attributes.image_url);
  }
  expect(seenImages.size).toBe(product.skus.length);
  await page.getByRole('button', {name: initialSku.label, exact: true}).click();
  await expect(image).toHaveAttribute('src', initialSku.attributes.image_url);
  expect(await page.getByRole('button', {name: 'Add to cart', exact: true}).evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
  await page.getByRole('button', {name: 'Increase quantity', exact: true}).click();
  await page.getByRole('button', {name: 'Add to cart', exact: true}).click();
  const badge = page.getByTestId('cart-count');
  await expect(badge).toHaveText('2');
  await expect(page.getByRole('link', {name: 'Shopping cart, 2 items', exact: true})).toBeVisible();
  const badgeBox = await badge.boundingBox();
  const iconBox = await page.locator('.cart-icon-wrap > svg').boundingBox();
  expect(badgeBox).not.toBeNull();
  expect(iconBox).not.toBeNull();
  expect(Math.abs(badgeBox!.width - badgeBox!.height)).toBeLessThanOrEqual(1);
  expect(badgeBox!.x + badgeBox!.width / 2).toBeGreaterThan(iconBox!.x + iconBox!.width / 2);
  expect(badgeBox!.y + badgeBox!.height / 2).toBeLessThan(iconBox!.y + iconBox!.height / 2);
  expect(await badge.evaluate(element => parseFloat(getComputedStyle(element).borderRadius))).toBeGreaterThanOrEqual(badgeBox!.height / 2);
  await page.screenshot({path: '../docs/screenshots/electronics-variant-desktop.png', fullPage: true});
  await page.reload();
  await expect(page.getByTestId('cart-count')).toHaveText('2');
  await page.getByRole('link', {name: 'Shopping cart, 2 items', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Your shopping cart', exact: true})).toBeVisible();
  await expect(page.locator('.cart-item img').first()).toHaveAttribute('src', initialSku.attributes.image_url);
  await expect(page.locator('.cart-item img').first()).toHaveAttribute('alt', `${product.name} — ${initialSku.label}`);
  await page.setViewportSize({width: 390, height: 844});
  for (const path of ['/', '/products/' + product.slug, '/cart']) {
    await page.goto(path);
    await expect(page.getByRole('link', {name: 'Shopping cart, 2 items', exact: true})).toBeVisible();
    if (path === '/') await expect(page.getByTestId('product-card').first()).toBeVisible();
    else if (path === '/cart') await expect(page.locator('.cart-item').first()).toBeVisible();
    else await expect(page.getByTestId('variant-product-image')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${path} fits a 390px mobile viewport`).toBeTruthy();
  }
  await page.screenshot({path: '../docs/screenshots/electronics-cart-mobile.png', fullPage: true});
});

test('guest purchase to COD settlement, partial return, refund and reconciled analytics', async ({page, playwright, baseURL}) => {
  const staff = await playwright.request.newContext({baseURL});
  await login(staff);
  const catalogue = await (await staff.get(`/api/v1/catalog/products/?q=${electronicsQuery}&page_size=24`)).json();
  const product = catalogue.results.find((item: any) => item.skus.some((sku: any) => sku.available >= 2));
  expect(product).toBeTruthy();
  const date = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Dhaka', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
  const filter = `analytics/?start=${date}&end=${date}&product_ids=${product.id}`;
  const before = await (await staff.get('/api/v1/' + filter)).json();
  await page.goto('/products/' + product.slug);
  await expect(page.getByRole('button', {name: 'Add to cart', exact: true})).toBeEnabled();
  await page.getByRole('button', {name: 'Increase quantity'}).click();
  await page.getByRole('button', {name: 'Add to cart', exact: true}).click();
  await page.getByRole('link', {name: 'View your cart'}).click();
  await page.getByRole('link', {name: /checkout/i}).click();
  await page.getByLabel('Full name', {exact: true}).fill('Synthetic E2E Customer');
  await page.getByLabel('Phone number').fill('01700000000');
  await page.getByLabel('Street address').fill('Synthetic House 10, Road 2');
  await page.getByLabel('Area / neighbourhood').fill('Synthetic Area');
  await page.getByLabel('City / district').fill('Chattogram');
  const checkoutResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/checkout/') && response.request().method() === 'POST');
  await page.getByRole('button', {name: /Place demo order|Place order/}).click();
  const result = await (await checkoutResponse).json();
  expect(result.order.status).toBe('confirmed');
  await expect(page).toHaveURL(/\/orders\//);
  const order = result.order;
  const route = `staff/orders/${order.id}/action/`;
  await mutation(staff, route, {action: 'prepare'});
  await mutation(staff, route, {action: 'dispatch', carrier: 'Synthetic courier', tracking_number: 'E2E-' + order.number});
  await mutation(staff, route, {action: 'deliver'});
  await mutation(staff, route, {action: 'collect_cod', amount: order.grand_total, reference: 'Synthetic collection ' + order.number});
  await mutation(staff, route, {action: 'settle_cod', amount: order.grand_total, reference: 'Synthetic settlement ' + order.number});
  await page.reload();
  await page.getByRole('button', {name: 'Request an item return'}).click();
  await page.locator('.return-form input[type="number"]').first().fill('1');
  await page.getByLabel('Return reason').selectOption('damaged');
  const returnResponse = page.waitForResponse(response => response.url().includes('/returns/') && response.request().method() === 'POST');
  await page.getByRole('button', {name: 'Submit return request'}).click();
  const returned = await (await returnResponse).json();
  expect(returned.status).toBe('requested');
  await mutation(staff, `staff/returns/${returned.id}/action/`, {action: 'approve'});
  await mutation(staff, `staff/returns/${returned.id}/action/`, {action: 'receive'});
  await mutation(staff, `staff/returns/${returned.id}/action/`, {action: 'inspect', lines: [{id: returned.lines[0].id, accepted_quantity: 1, restock_quantity: 1, disposition: 'restock'}]});
  const pendingRefund = await (await staff.get('/api/v1/' + filter)).json();
  expect(pendingRefund.summary.returned_units - before.summary.returned_units).toBe(1);
  expect(Number(pendingRefund.summary.returned_value)).toBeGreaterThan(Number(before.summary.returned_value));
  expect(pendingRefund.summary.refunded_amount).toBe(before.summary.refunded_amount);
  const updated = await (await staff.get(`/api/v1/staff/orders/${order.id}/`)).json();
  expect(updated.lines[0].returned_quantity).toBe(1);
  await mutation(staff, `staff/refunds/${updated.refunds[0].id}/confirm/`, {reference: 'Synthetic verified refund ' + order.number});
  const after = await (await staff.get('/api/v1/' + filter)).json();
  expect(after.summary.net_delivered_value).toBe(pendingRefund.summary.net_delivered_value);
  expect(after.summary.delivered_units - before.summary.delivered_units).toBe(2);
  expect(after.summary.returned_units - before.summary.returned_units).toBe(1);
  const exported = await staff.get(`/api/v1/analytics/export/?metric=delivered_units&start=${date}&end=${date}&product_ids=${product.id}`);
  expect(await exported.text()).toContain(order.number);
  expect(await exported.text()).not.toContain('01700000000');
  const outsider = await playwright.request.newContext({baseURL});
  expect((await outsider.get(`/api/v1/orders/${order.id}/`)).status()).toBe(403);
  await outsider.dispose();
  await staff.dispose();
});

test('analyst workspace exposes reports and protects operational customer records', async ({page}) => {
  await page.goto('/analytics');
  await page.getByLabel('Username', {exact: true}).fill('analyst');
  await page.getByLabel('Password', {exact: true}).fill(process.env.DEMO_VIEWER_PASSWORD || password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.locator('.stats-grid').first()).toBeVisible();
  expect((await page.request.get('/api/v1/staff/orders/')).status()).toBe(403);
  await expect(page.locator('.sidebar').getByRole('link', {name: 'Orders', exact: true})).toHaveCount(0);
  await page.screenshot({path: '../docs/screenshots/analytics-desktop.png', fullPage: true});
  await page.getByRole('button', {name: 'Product comparison', exact: true}).click();
  await page.locator('.product-filter summary').click();
  await page.locator('.product-filter input[type="checkbox"]').first().check();
  await page.locator('.product-filter summary').click();
  const variants = page.waitForResponse(response => response.url().includes('/api/v1/analytics/variants/'));
  await page.getByRole('button', {name: 'Apply filters', exact: true}).click();
  expect((await variants).status()).toBe(200);
  await expect(page.getByRole('region', {name: 'SKU performance'}).getByRole('columnheader', {name: 'SKU', exact: true})).toBeVisible();
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});

test('staff order drawer prepares and cancels an order through real validated actions', async ({page, playwright, baseURL}) => {
  const guest = await playwright.request.newContext({baseURL});
  const bootstrap = await (await guest.get('/api/v1/bootstrap/')).json();
  const catalogue = await (await guest.get(`/api/v1/catalog/products/?q=${electronicsQuery}`)).json();
  const product = catalogue.results.find((p: any) => p.skus.some((s: any) => s.available > 1));
  const sku = product.skus.find((s: any) => s.available > 1);
  await mutation(guest, 'cart/', {sku_id: sku.id, quantity: 1});
  const token = (await (await guest.get('/api/v1/bootstrap/')).json()).csrfToken;
  const response = await guest.post('/api/v1/checkout/', {headers: {'X-CSRFToken': token, 'Idempotency-Key': 'staff-ui-' + Date.now()}, data: {
    customer_name: 'Synthetic staff workflow', email: '', phone: '01700000000',
    address: {line1:'Synthetic test address',city:'Chattogram'},
    delivery_zone_id: bootstrap.delivery_zones[0].id, payment_method:'cod',
  }});
  expect(response.status(), await response.text()).toBe(201);
  const {order} = await response.json();
  await page.goto('/staff/orders');
  await page.getByLabel('Username', {exact:true}).fill('administrator');
  await page.getByLabel('Password', {exact:true}).fill(password);
  await page.getByRole('button', {name:'Sign in',exact:true}).click();
  await page.getByPlaceholder('Search order or customer…').fill(order.number);
  await page.getByRole('button', {name:order.number,exact:true}).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('combobox', {name:'Operation',exact:true}).selectOption('prepare');
  await dialog.getByRole('button', {name:'Record event',exact:true}).click();
  await expect(dialog.locator('.badge.status-preparing')).toBeVisible();
  await dialog.getByRole('combobox', {name:'Operation',exact:true}).selectOption('cancel');
  await dialog.locator('input[type="number"]').first().fill('1');
  await dialog.getByRole('button', {name:'Record event',exact:true}).click();
  await expect(dialog.locator('.badge.status-cancelled')).toBeVisible();
  await page.screenshot({path:'../docs/screenshots/staff-order.png',fullPage:true});
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await page.goto('/staff');
  await expect(page.getByRole('region', {name:'Operations health'}).getByText('COD orders waiting 48+ hours', {exact:true})).toBeVisible();
  await guest.dispose();
});

test('administrator reviews and queues a historical correction without changing live stock', async ({page, playwright, baseURL}) => {
  const staff = await playwright.request.newContext({baseURL});
  await login(staff);
  const catalogue = await (await staff.get(`/api/v1/catalog/products/?q=${electronicsQuery}`)).json();
  const product = catalogue.results[0];
  const sku = product.skus[0];
  const source = 'synthetic-e2e-revision-' + Date.now();
  const observed = new Date(Date.now() - 3600_000).toISOString();
  async function upload(price: number) {
    const bootstrap = await (await staff.get('/api/v1/bootstrap/')).json();
    const csv = 'source_order_id,source_line_id,sku,ordered_at,status,payment_method,quantity,unit_price,shipped_quantity,delivered_quantity,delivered_at\n' +
      `order-1,line-1,${sku.code},${observed},delivered,cod,1,${price},1,1,${observed}\n`;
    const response = await staff.post('/api/v1/imports/', {headers: {'X-CSRFToken': bootstrap.csrfToken}, multipart: {
      kind: 'history', source_name: source, files: {name: 'history.csv', mimeType: 'text/csv', buffer: Buffer.from(csv)},
    }});
    expect(response.status(), await response.text()).toBe(202);
    return (await response.json()).id;
  }
  async function status(id: string) { return (await (await staff.get(`/api/v1/imports/${id}/`)).json()).status; }
  const first = await upload(100);
  await expect.poll(() => status(first), {timeout: 30_000}).toBe('ready');
  await mutation(staff, `imports/${first}/commit/`, {});
  await expect.poll(() => status(first), {timeout: 30_000}).toBe('completed');
  const second = await upload(150);
  await expect.poll(() => status(second), {timeout: 30_000}).toBe('failed');
  await page.goto('/imports');
  await page.getByLabel('Username', {exact: true}).fill('administrator');
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await page.getByRole('row').filter({hasText: source}).first().getByRole('button', {name: 'history.csv', exact: true}).click();
  await page.getByRole('button', {name: 'Review historical correction', exact: true}).click();
  const review = page.getByRole('region', {name: 'Historical correction review'});
  await expect(review.getByRole('cell', {name: 'revise', exact: true})).toBeVisible();
  await review.getByLabel('Reason for historical correction').fill('Synthetic verification: source export price corrected against original record.');
  await review.getByRole('button', {name: 'Authorize historical revision', exact: true}).click();
  await expect.poll(() => status(second), {timeout: 30_000}).toBe('completed');
  const current = await (await staff.get(`/api/v1/catalog/products/${product.slug}/`)).json();
  expect(current.skus.find((item: any) => item.id === sku.id).available).toBe(sku.available);
  await staff.dispose();
});
