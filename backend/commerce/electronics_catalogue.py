"""Synthetic electronics catalogue shared by the fresh seed and safe curation.

These are fictional demonstration products, not manufacturer specifications or
live merchant stock. Colour image paths are served by the frontend's public
assets and deliberately live on each SKU, rather than being inferred by CSS.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ElectronicsFamily:
    key: str
    name: str
    category: str
    price: int
    description: str


COLORS = (
    ("black", "Black", "#252b32"),
    ("silver", "Silver", "#c7cdd3"),
    ("blue", "Blue", "#416d94"),
)

FAMILIES = (
    ElectronicsFamily("laptop", "VertexBook 14", "Laptops & PCs", 74900,
                      "A compact 14-inch notebook with 16 GB memory and a 512 GB SSD for work, study and everyday projects."),
    ElectronicsFamily("tablet", "SlateTab 11", "Mobile & Tablets", 26900,
                      "An 11-inch tablet with 128 GB storage for reading, video calls and taking your work along."),
    ElectronicsFamily("headphones", "Studio Wireless Headphones", "Audio", 4990,
                      "Over-ear wireless headphones with cushioned ear cups, USB-C charging and a folding headband."),
    ElectronicsFamily("earbuds", "Pocket Wireless Earbuds", "Audio", 2490,
                      "Compact wireless earbuds with a charging case and touch controls for daily listening."),
    ElectronicsFamily("speaker", "Pulse Portable Speaker", "Audio", 3490,
                      "A portable Bluetooth speaker with a woven grille, simple controls and USB-C charging."),
    ElectronicsFamily("camera", "Focus Mirrorless Camera", "Cameras", 58900,
                      "A compact mirrorless camera with a standard zoom lens for everyday photography and video."),
    ElectronicsFamily("smartwatch", "Stride Smartwatch", "Tools & Gadgets", 3990,
                      "A lightweight smartwatch with an adjustable strap, activity tracking and phone notifications."),
    ElectronicsFamily("phone", "Nova Mobile 128", "Mobile & Tablets", 21900,
                      "An everyday smartphone with 128 GB storage, a dual-camera layout and USB-C charging."),
    ElectronicsFamily("keyboard", "Type Mechanical Keyboard", "Laptops & PCs", 4290,
                      "A compact mechanical keyboard with tactile keys, a detachable USB-C cable and a durable frame."),
    ElectronicsFamily("mouse", "Point Wireless Mouse", "Laptops & PCs", 1490,
                      "A comfortable wireless mouse with quiet buttons, an adjustable pointer speed and USB-C charging."),
    ElectronicsFamily("charger", "Charge 65W USB-C Adapter", "Accessories", 2290,
                      "A compact 65 W USB-C power adapter for compatible laptops, tablets and phones."),
    ElectronicsFamily("screwdriver", "Precision Electric Screwdriver", "Tools & Gadgets", 2790,
                      "A rechargeable precision screwdriver and interchangeable bits for small electronics projects."),
    ElectronicsFamily("hub", "Connect 7-in-1 USB-C Hub", "Accessories", 3290,
                      "A compact desktop hub with USB, HDMI and card-reader connections for a compatible USB-C computer."),
    ElectronicsFamily("smart-camera", "Home Indoor Smart Camera", "Smart Home", 2990,
                      "A compact indoor Wi-Fi camera with an adjustable stand and phone-based viewing."),
)

SPECIFICATIONS = {
    "laptop": "14-inch · 16 GB / 512 GB SSD",
    "tablet": "11-inch · 128 GB",
    "headphones": "Wireless · Over-ear",
    "earbuds": "Wireless · Charging case",
    "speaker": "Bluetooth · USB-C",
    "camera": "Mirrorless · Zoom lens",
    "smartwatch": "Activity tracking · Adjustable strap",
    "phone": "128 GB · USB-C",
    "keyboard": "Mechanical · USB-C",
    "mouse": "Wireless · Quiet buttons",
    "charger": "65 W · USB-C",
    "screwdriver": "Rechargeable · Precision bits",
    "hub": "7-in-1 · USB-C",
    "smart-camera": "Indoor · Wi-Fi",
}


def image_url(family, color):
    return f"/products/electronics/{family}-{color}.svg"


def variant_attributes(family, color):
    key, label, hex_value = color
    return {"color": label, "color_hex": hex_value, "image_url": image_url(family.key, key),
            "specification": SPECIFICATIONS[family.key], "synthetic": True}
