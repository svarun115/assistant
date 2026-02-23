"""
Generate icon for MCP Server Manager
Run once: python generate_icon.py
Requires: pip install Pillow
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # Create multiple sizes for ICO file
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        # Create image with gradient-like background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background rounded rectangle (dark blue/purple gradient feel)
        padding = size // 8
        corner_radius = size // 4

        # Draw rounded rectangle background
        bg_color = (79, 70, 229)  # Indigo/purple
        draw.rounded_rectangle(
            [padding, padding, size - padding, size - padding],
            radius=corner_radius,
            fill=bg_color
        )

        # Draw server stack icon
        center_x = size // 2
        center_y = size // 2

        # Server box dimensions
        box_width = int(size * 0.5)
        box_height = int(size * 0.12)
        gap = int(size * 0.04)

        # Three stacked server boxes
        server_color = (255, 255, 255)  # White
        dot_color = (34, 197, 94)  # Green for status dots

        for i in range(3):
            y_offset = (i - 1) * (box_height + gap)
            box_y = center_y + y_offset - box_height // 2

            # Server box
            draw.rounded_rectangle(
                [center_x - box_width // 2, box_y,
                 center_x + box_width // 2, box_y + box_height],
                radius=size // 16,
                fill=server_color
            )

            # Status dot on each server
            dot_radius = max(1, size // 20)
            dot_x = center_x + box_width // 2 - dot_radius * 3
            dot_y = box_y + box_height // 2
            draw.ellipse(
                [dot_x - dot_radius, dot_y - dot_radius,
                 dot_x + dot_radius, dot_y + dot_radius],
                fill=dot_color
            )

        images.append(img)

    # Save as ICO
    icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
    images[0].save(
        icon_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print(f"Icon saved to: {icon_path}")

    return icon_path

if __name__ == "__main__":
    create_icon()
