"use client";

import { useId, useState } from "react";
import { ImageOff } from "lucide-react";
import {
  electronicsImageFamilies,
  electronicsImageLibrary,
  imageSourceError,
  type ProductImageChoice,
} from "@/lib/product-images";
import { Field } from "./ui";

export function ProductImagePicker({
  label,
  value,
  onChange,
  fallback = "",
  fallbackLabel = "Product image",
  allowInherit = false,
}: {
  label: "Product image" | "Variant image";
  value: string;
  onChange: (value: string, choice?: ProductImageChoice) => void;
  fallback?: string;
  fallbackLabel?: string;
  allowInherit?: boolean;
}) {
  const descriptionId = useId();
  const [failedSource, setFailedSource] = useState("");
  const validationError = imageSourceError(value);
  const previewSource = value || fallback;
  const previewError = imageSourceError(previewSource);
  const failed = Boolean(previewSource && failedSource === previewSource);
  const selected = electronicsImageLibrary.find((image) => image.url === value);
  return (
    <div className="product-image-editor">
      <div className="image-editor-controls">
        <Field label={`${label} library`}>
          <select
            aria-label={`${label} library`}
            value={selected?.url || ""}
            onChange={(event) => {
              const image = electronicsImageLibrary.find(
                (choice) => choice.url === event.target.value,
              );
              if (image) onChange(image.url, image);
            }}
          >
            <option value="" disabled>
              {value ? "Custom / current image" : "Choose an electronics image"}
            </option>
            {electronicsImageFamilies.map(([family, familyLabel]) => (
              <optgroup key={family} label={familyLabel}>
                {electronicsImageLibrary
                  .filter((image) => image.family === family)
                  .map((image) => (
                    <option key={image.url} value={image.url}>
                      {image.label}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </Field>
        <Field label={`${label} URL`}>
          <input
            type="text"
            inputMode="url"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={value}
            maxLength={1000}
            placeholder={
              allowInherit
                ? "Leave blank to use the product image"
                : "/products/electronics/laptop-black.svg"
            }
            aria-describedby={descriptionId}
            aria-invalid={validationError ? true : undefined}
            onChange={(event) => onChange(event.target.value)}
          />
        </Field>
        <p className="image-editor-caption muted" id={descriptionId}>
          {validationError ||
            "Choose a library image or enter a public /products/ path or HTTPS image URL."}
        </p>
        {allowInherit && (
          <button
            type="button"
            className="text-link image-inherit-action"
            onClick={() => onChange("")}
            disabled={!value}
          >
            Use product image
          </button>
        )}
      </div>
      <figure className="image-editor-preview">
        {previewSource && !previewError && !failed ? (
          <img
            key={previewSource}
            src={previewSource}
            alt={`${label} preview`}
            onError={() => setFailedSource(previewSource)}
          />
        ) : (
          <div className="image-preview-empty" role="status">
            <ImageOff size={25} aria-hidden="true" />
            <span>
              {previewError
                ? "Enter a valid image URL to preview."
                : failed
                  ? "Image could not load. Check the public image URL."
                  : "No image selected"}
            </span>
            {failed && !previewError && (
              <button
                type="button"
                className="text-link"
                onClick={() => setFailedSource("")}
              >
                Retry preview
              </button>
            )}
          </div>
        )}
        <figcaption>
          {allowInherit && !value
            ? `Using ${fallbackLabel.toLowerCase()}`
            : label}
        </figcaption>
      </figure>
    </div>
  );
}
