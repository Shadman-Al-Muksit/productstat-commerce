import {test, expect, type APIRequestContext} from '@playwright/test';

const password = process.env.DEMO_PASSWORD || 'ProductStatDemo!2026';
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
  await page.goto('/');
  await expect(page.locator('a[href^="/products/"]').first()).toBeVisible();
  await page.getByRole('button', {name: 'Switch language'}).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'bn');
  await page.getByRole('button', {name: 'Switch language'}).click();
  const search = page.getByRole('textbox', {name: 'Search products'});
  await search.fill('Everyday Tote');
  await expect(page.locator('a[href^="/products/"]').first()).toContainText('Everyday Tote');
  await page.screenshot({path: '../docs/screenshots/storefront-desktop.png', fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  await expect(page.locator('a[href^="/products/"]').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  await page.screenshot({path: '../docs/screenshots/storefront-mobile.png', fullPage: true});
});

test('guest purchase to COD settlement, partial return, refund and reconciled analytics', async ({page, playwright, baseURL}) => {
  const staff = await playwright.request.newContext({baseURL});
  await login(staff);
  const catalogue = await (await staff.get('/api/v1/catalog/products/?q=Everyday%20Tote&page_size=24')).json();
  const product = catalogue.results.find((item: any) => item.skus.some((sku: any) => sku.available >= 2));
  expect(product).toBeTruthy();
  const date = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Dhaka', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
  const filter = `analytics/?start=${date}&end=${date}&product_ids=${product.id}`;
  const before = await (await staff.get('/api/v1/' + filter)).json();
  await page.goto('/products/' + product.slug);
  await expect(page.getByRole('button', {name: 'Add to bag', exact: true})).toBeEnabled();
  await page.getByRole('button', {name: 'Increase quantity'}).click();
  await page.getByRole('button', {name: 'Add to bag', exact: true}).click();
  await page.getByRole('link', {name: 'View your bag'}).click();
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
  const updated = await (await staff.get(`/api/v1/staff/orders/${order.id}/`)).json();
  expect(updated.lines[0].returned_quantity).toBe(1);
  await mutation(staff, `staff/refunds/${updated.refunds[0].id}/confirm/`, {reference: 'Synthetic verified refund ' + order.number});
  const after = await (await staff.get('/api/v1/' + filter)).json();
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
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});

test('staff order drawer prepares and cancels an order through real validated actions', async ({page, playwright, baseURL}) => {
  const guest = await playwright.request.newContext({baseURL});
  const bootstrap = await (await guest.get('/api/v1/bootstrap/')).json();
  const catalogue = await (await guest.get('/api/v1/catalog/products/?q=Everyday%20Tote')).json();
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
  await dialog.getByLabel('Operation', {exact:true}).selectOption('prepare');
  await dialog.getByRole('button', {name:'Record event',exact:true}).click();
  await expect(dialog.locator('.badge.status-preparing')).toBeVisible();
  await dialog.getByLabel('Operation', {exact:true}).selectOption('cancel');
  await dialog.locator('input[type="number"]').first().fill('1');
  await dialog.getByRole('button', {name:'Record event',exact:true}).click();
  await expect(dialog.locator('.badge.status-cancelled')).toBeVisible();
  await page.screenshot({path:'../docs/screenshots/staff-order.png',fullPage:true});
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await guest.dispose();
});
