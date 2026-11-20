import { test, expect, type APIRequestContext } from "@playwright/test";

const password = process.env.DEMO_PASSWORD || "ProductStatDemo!2026";
async function mutate(
  context: APIRequestContext,
  path: string,
  data: unknown,
  method = "POST",
) {
  const bootstrap = await (await context.get("/api/v1/bootstrap/")).json();
  const response = await context.fetch("/api/v1/" + path, {
    method,
    data,
    headers: { "X-CSRFToken": bootstrap.csrfToken },
  });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}
async function login(context: APIRequestContext, username = "administrator") {
  await mutate(context, "auth/login/", { username, password });
}

test("homepage spotlight uses catalogue pricing and handles unavailable selection", async ({
  page,
}) => {
  const catalogue = await (
    await page.request.get(
      "/api/v1/catalog/products/?q=Studio%20Wireless%20Headphones",
    )
  ).json();
  const headphones = catalogue.results.find(
    (item: any) => item.name === "Studio Wireless Headphones",
  );
  expect(headphones).toBeTruthy();
  await page.goto("/");
  const spotlight = page.locator(".featured-electronics");
  const expectedPrice =
    "৳" +
    new Intl.NumberFormat("en-BD", { maximumFractionDigits: 2 }).format(
      Number(headphones.min_price),
    );
  await expect(spotlight.locator(".featured-price strong")).toHaveText(
    expectedPrice,
  );
  await expect(
    spotlight.getByRole("link", { name: "View headphones", exact: true }),
  ).toHaveAttribute("href", "/products/" + headphones.slug);
  await page
    .locator(".hero-art img")
    .evaluate((img: HTMLImageElement) => img.decode());
  await expect(page.getByTestId("product-card").first()).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/homepage-preview.png",
    fullPage: false,
  });
  await page
    .getByRole("link", { name: "Explore laptops", exact: true })
    .click();
  await expect(
    page.getByTestId("product-card").first().locator(".product-category"),
  ).toHaveText("Laptops & PCs");
  expect(new URL(page.url()).searchParams.get("category")).toBe(
    "Laptops & PCs",
  );
  await page
    .getByRole("link", { name: "Shop electronics", exact: true })
    .click();
  await expect
    .poll(() => page.getByTestId("product-card").count())
    .toBeGreaterThan(3);
  await page.route("**/api/v1/catalog/products/**", async (route) => {
    const requestUrl = new URL(route.request().url());
    if (
      requestUrl.searchParams.get("q") === "Studio Wireless Headphones" &&
      !requestUrl.searchParams.has("page")
    ) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Synthetic unavailable selection" }),
      });
    } else await route.continue();
  });
  await page.reload();
  await expect(spotlight.locator(".featured-price")).toContainText(
    "Featured selection is currently unavailable.",
  );
  await expect(spotlight.locator(".featured-price strong")).toHaveCount(0);
  await expect(
    spotlight.getByRole("link", { name: "View headphones", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByTestId("product-card").first()).toBeVisible();
});

test("operator cannot bypass courier settlement permissions through the API", async ({
  page,
  playwright,
  baseURL,
}) => {
  const staff = await playwright.request.newContext({ baseURL });
  const guest = await playwright.request.newContext({ baseURL });
  await login(staff);
  const bootstrap = await (await guest.get("/api/v1/bootstrap/")).json();
  const catalogue = await (
    await guest.get(
      "/api/v1/catalog/products/?q=Studio%20Wireless%20Headphones",
    )
  ).json();
  const product = catalogue.results.find((item: any) =>
    item.skus.some((sku: any) => sku.available >= 1),
  );
  const sku = product.skus.find((item: any) => item.available >= 1);
  await mutate(guest, "cart/", { sku_id: sku.id, quantity: 1 });
  const token = (await (await guest.get("/api/v1/bootstrap/")).json())
    .csrfToken;
  const placed = await guest.post("/api/v1/checkout/", {
    headers: {
      "X-CSRFToken": token,
      "Idempotency-Key": "qa-settlement-guard-" + Date.now(),
    },
    data: {
      customer_name: "Synthetic settlement guard",
      phone: "01700000000",
      email: "",
      address: { line1: "Synthetic QA House", city: "Chattogram" },
      delivery_zone_id: bootstrap.delivery_zones[0].id,
      payment_method: "cod",
    },
  });
  expect(placed.status()).toBe(201);
  const { order } = await placed.json();
  const path = `staff/orders/${order.id}/action/`;
  await mutate(staff, path, { action: "prepare" });
  await mutate(staff, path, {
    action: "dispatch",
    carrier: "Synthetic courier",
    tracking_number: "QA-" + order.number,
  });
  await mutate(staff, path, { action: "deliver" });
  await mutate(staff, path, {
    action: "collect_cod",
    amount: order.grand_total,
    reference: "QA-COLLECT-" + order.number,
  });

  await page.goto("/staff/orders");
  await page.getByLabel("Username", { exact: true }).fill("operator");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByPlaceholder("Search order or customer…").fill(order.number);
  await page.getByRole("button", { name: order.number, exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog
      .getByRole("combobox", { name: "Operation", exact: true })
      .locator('option[value="settle_cod"]'),
  ).toHaveCount(0);
  const before = await (
    await staff.get(`/api/v1/staff/orders/${order.id}/`)
  ).json();
  const operatorToken = (
    await (await page.request.get("/api/v1/bootstrap/")).json()
  ).csrfToken;
  const denied = await page.request.post("/api/v1/" + path, {
    headers: { "X-CSRFToken": operatorToken },
    data: {
      action: "settle_cod",
      amount: order.grand_total,
      reference: "QA-DENIED-" + order.number,
    },
  });
  expect(denied.status()).toBe(403);
  const unchanged = await (
    await staff.get(`/api/v1/staff/orders/${order.id}/`)
  ).json();
  expect(unchanged.payments).toEqual(before.payments);
  expect(unchanged.settled_total).toBe(before.settled_total);
  expect(unchanged.status).toBe(before.status);
  const settled = await mutate(staff, path, {
    action: "settle_cod",
    amount: order.grand_total,
    reference: "QA-ADMIN-" + order.number,
  });
  expect(Number(settled.settled_total)).toBe(Number(order.grand_total));
  await guest.dispose();
  await staff.dispose();
});

test("staff product and variant image editor persists previews, colours and metadata", async ({
  page,
  playwright,
  baseURL,
}) => {
  const staff = await playwright.request.newContext({ baseURL });
  await login(staff);
  const stamp = Date.now();
  const customImage = "https://images.example.invalid/qa-headphones.svg";
  await page.route("https://images.example.invalid/**", (route) =>
    route.request().url().endsWith("/missing.svg")
      ? route.fulfill({ status: 404, body: "Synthetic missing image" })
      : route.fulfill({
          contentType: "image/svg+xml",
          body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><rect x="40" y="40" width="120" height="120" rx="30" fill="#416d94"/></svg>',
        }),
  );
  const created = await mutate(staff, "staff/products/", {
    name: "Synthetic QA Image Editor " + stamp,
    slug: "qa-image-editor-" + stamp,
    category: "Audio",
    description: "Synthetic image editor verification product.",
    is_active: true,
    image_url: "/products/electronics/headphones-black.svg",
    skus: [
      {
        code: "QA-IMG-BLACK-" + stamp,
        label: "Black",
        price: "4990.00",
        attributes: {
          color: "Black",
          color_hex: "#252b32",
          image_url: "/products/electronics/headphones-black.svg",
          specification: "Synthetic preserved specification",
          synthetic: true,
          supplier_metadata: { marker: "retain-me" },
        },
      },
      {
        code: "QA-IMG-CUSTOM-" + stamp,
        label: "Custom finish / 128 GB",
        price: "5990.00",
        attributes: {
          color: "Silver",
          color_hex: "#c7cdd3",
          image_url: "",
          specification: "Synthetic custom label",
          synthetic: true,
        },
      },
    ],
  });
  const baselineStock = await (
    await staff.get(
      "/api/v1/staff/inventory/?q=" + encodeURIComponent(created.name),
    )
  ).json();
  try {
    await page.goto("/staff/products");
    await page.getByLabel("Username", { exact: true }).fill("administrator");
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByPlaceholder("Search products or SKUs…").fill(created.name);
    await page
      .getByRole("row")
      .filter({ hasText: created.name })
      .getByRole("button", { name: "Edit", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByLabel("Product image URL", { exact: true }),
    ).toHaveValue(created.image_url);
    await expect(
      dialog.getByLabel("Product image library", { exact: true }),
    ).toHaveValue(created.image_url);
    await dialog
      .getByLabel("Product image library", { exact: true })
      .selectOption("/products/electronics/headphones-silver.svg");
    await expect(
      dialog.getByRole("img", { name: "Product image preview", exact: true }),
    ).toHaveAttribute("src", "/products/electronics/headphones-silver.svg");
    await dialog
      .getByLabel("Product image URL", { exact: true })
      .fill("https://images.example.invalid/missing.svg");
    const productImagePicker = dialog.locator(".product-image-editor").first();
    await expect(
      productImagePicker.getByText(
        "Image could not load. Check the public image URL.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      productImagePicker.getByRole("button", {
        name: "Retry preview",
        exact: true,
      }),
    ).toBeVisible();
    await dialog
      .getByLabel("Product image URL", { exact: true })
      .fill(customImage);
    await expect
      .poll(() =>
        dialog
          .getByRole("img", { name: "Product image preview", exact: true })
          .evaluate(
            (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
          ),
      )
      .toBeTruthy();
    const groups = dialog.locator("fieldset.variant-editor");
    let colourGroup = groups.first();
    let customGroup = groups.last();
    for (let index = 0; index < (await groups.count()); index++) {
      if (
        (
          await groups
            .nth(index)
            .getByLabel("SKU code", { exact: true })
            .inputValue()
        ).startsWith("QA-IMG-BLACK-")
      )
        colourGroup = groups.nth(index);
      else customGroup = groups.nth(index);
    }
    await colourGroup
      .getByLabel("Variant image library", { exact: true })
      .selectOption("/products/electronics/headphones-blue.svg");
    await expect(
      colourGroup.getByLabel("Colour name", { exact: true }),
    ).toHaveValue("Blue");
    await expect(
      colourGroup.getByLabel("Colour hex", { exact: true }),
    ).toHaveValue("#416d94");
    await expect(
      colourGroup.getByLabel("Variant label", { exact: true }),
    ).toHaveValue("Blue");
    await customGroup
      .getByLabel("Variant image library", { exact: true })
      .selectOption("/products/electronics/headphones-black.svg");
    await expect(
      customGroup.getByLabel("Variant label", { exact: true }),
    ).toHaveValue("Custom finish / 128 GB");
    await customGroup
      .getByRole("button", { name: "Use product image", exact: true })
      .click();
    await expect(
      customGroup.getByLabel("Variant image URL", { exact: true }),
    ).toHaveValue("");
    await expect(
      customGroup.getByRole("img", {
        name: "Variant image preview",
        exact: true,
      }),
    ).toHaveAttribute("src", customImage);
    await dialog
      .getByRole("button", { name: "Save product", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    const saved = await (
      await staff.get(`/api/v1/staff/products/${created.id}/`)
    ).json();
    expect(saved.image_url).toBe(customImage);
    const blue = saved.skus.find((item: any) =>
      item.code.startsWith("QA-IMG-BLACK-"),
    );
    const custom = saved.skus.find((item: any) =>
      item.code.startsWith("QA-IMG-CUSTOM-"),
    );
    expect(blue.attributes).toMatchObject({
      color: "Blue",
      color_hex: "#416d94",
      image_url: "/products/electronics/headphones-blue.svg",
      specification: "Synthetic preserved specification",
      synthetic: true,
      supplier_metadata: { marker: "retain-me" },
    });
    expect(custom.label).toBe("Custom finish / 128 GB");
    expect(custom.attributes.image_url).toBe("");
    const afterStock = await (
      await staff.get(
        "/api/v1/staff/inventory/?q=" + encodeURIComponent(created.name),
      )
    ).json();
    const balances = (response: any) =>
      response.results.map((row: any) => ({
        id: row.id,
        code: row.code,
        on_hand: row.on_hand,
        reserved: row.reserved,
        available: row.available,
        price: row.price,
      }));
    expect(afterStock.count).toBe(baselineStock.count);
    expect(balances(afterStock)).toEqual(balances(baselineStock));

    await page
      .getByRole("row")
      .filter({ hasText: created.name })
      .getByRole("button", { name: "Edit", exact: true })
      .click();
    await expect(
      dialog.getByLabel("Product image URL", { exact: true }),
    ).toHaveValue(customImage);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await dialog.evaluate(
        (element) => element.scrollWidth <= element.clientWidth + 1,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: "../docs/screenshots/staff-image-editor-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({
      path: "../docs/screenshots/staff-image-editor-desktop.png",
      fullPage: true,
    });
    await dialog
      .locator("fieldset.variant-editor")
      .first()
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "../docs/screenshots/staff-variant-image-editor-desktop.png",
      fullPage: true,
    });
    await dialog
      .getByRole("button", { name: "Close details", exact: true })
      .click();
    await page.goto("/products/" + created.slug);
    await page.getByRole("button", { name: "Blue", exact: true }).click();
    await expect(page.getByTestId("variant-product-image")).toHaveAttribute(
      "src",
      blue.attributes.image_url,
    );
    await page
      .getByRole("button", { name: "Custom finish / 128 GB", exact: true })
      .click();
    await expect(page.getByTestId("variant-product-image")).toHaveAttribute(
      "src",
      customImage,
    );
  } finally {
    await mutate(
      staff,
      `staff/products/${created.id}/`,
      { is_active: false },
      "PATCH",
    );
    await staff.dispose();
  }
});
