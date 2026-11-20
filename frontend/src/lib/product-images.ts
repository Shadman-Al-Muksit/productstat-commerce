export const electronicsImageFamilies = [
  ["laptop", "Laptop"],
  ["tablet", "Tablet"],
  ["headphones", "Headphones"],
  ["earbuds", "Earbuds"],
  ["speaker", "Speaker"],
  ["camera", "Camera"],
  ["smartwatch", "Smartwatch"],
  ["phone", "Mobile phone"],
  ["keyboard", "Keyboard"],
  ["mouse", "Mouse"],
  ["charger", "USB-C charger"],
  ["screwdriver", "Electric screwdriver"],
  ["hub", "USB-C hub"],
  ["smart-camera", "Smart home camera"],
] as const;

export const electronicsImageColours = [
  { key: "black", name: "Black", hex: "#252b32" },
  { key: "silver", name: "Silver", hex: "#c7cdd3" },
  { key: "blue", name: "Blue", hex: "#416d94" },
] as const;

export const electronicsImageLibrary = electronicsImageFamilies.flatMap(
  ([family, label]) =>
    electronicsImageColours.map((colour) => ({
      url: `/products/electronics/${family}-${colour.key}.svg`,
      label: `${label} · ${colour.name}`,
      family,
      familyLabel: label,
      colour: colour.name,
      hex: colour.hex,
    })),
);

export type ProductImageChoice = (typeof electronicsImageLibrary)[number];
export const defaultProductImage = "/products/electronics/headphones-black.svg";

export function skuAttributes(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? { ...(value as Record<string, unknown>) }
    : {};
}

export function imageSourceError(value: string): string {
  if (!value) return "";
  if (value.length > 1000)
    return "Image URLs must be 1,000 characters or fewer.";
  if (/[\s\\\u0000-\u001f\u007f]/.test(value))
    return "Use an image URL without spaces, backslashes or control characters.";
  if (value.startsWith("/products/")) {
    try {
      const decodedPath = decodeURIComponent(value.split(/[?#]/, 1)[0]);
      if (
        decodedPath.split("/").some((part) => part === "." || part === "..") ||
        /[\\\u0000-\u001f\u007f]/.test(decodedPath)
      )
        return "Use a public image inside /products/.";
      return "";
    } catch {
      return "Use a valid public /products/ image path.";
    }
  }
  try {
    const url = new URL(value);
    if (
      url.protocol === "https:" &&
      url.hostname &&
      !url.username &&
      !url.password
    )
      return "";
  } catch {}
  return "Use a public /products/ image path or a complete HTTPS image URL.";
}

export function colourHexError(value: string): string {
  return !value || /^#(?:[\da-f]{3}|[\da-f]{6})$/i.test(value)
    ? ""
    : "Enter a colour such as #416d94, or leave it blank.";
}
