"""Booli field extraction (spider mixin)."""

from __future__ import annotations


class BooliMetadataMixin:
    def extract_description(self, response):
        try:
            desc_selectors = [
                ".description",
                ".property-description",
                '[data-test="description"]',
                ".listing-description",
            ]

            for selector in desc_selectors:
                try:
                    desc_text = response.css(f"{selector}::text").get()
                    if desc_text:
                        return desc_text.strip()
                except Exception:
                    self.logger.debug("Description selector failed: %s", selector, exc_info=True)
                    continue
        except Exception as e:
            self.logger.debug(f"Could not extract description: {e}")
        return None

    def extract_images(self, response):
        images = []
        try:
            image_elements = response.css(
                "img[src*='booli'], .gallery img, .property-images img::attr(src)"
            ).getall()
            for src in image_elements:
                if src and src.startswith("http"):
                    images.append(src)
        except Exception as e:
            self.logger.debug(f"Could not extract images: {e}")
        return images
