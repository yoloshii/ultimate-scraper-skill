"""Human-like behavioral simulation for browser automation.

Detection systems analyze behavior patterns beyond just fingerprints.
This module provides realistic human-like interactions:
- Bezier curve mouse movements (not linear)
- Variable typing speeds with typo patterns
- Reading time based on content length
- Natural pauses and scrolling behavior
"""

import random
import asyncio
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Any


@dataclass
class Point:
    """2D point for mouse movement."""
    x: float
    y: float


class BezierCurve:
    """Generate Bezier curve points for natural mouse movement.

    Linear mouse movements are a strong bot indicator.
    Bezier curves simulate the natural arc of human hand movement.
    """

    @staticmethod
    def generate_points(
        start: Tuple[int, int],
        end: Tuple[int, int],
        steps: int = 50,
        curvature: float = 0.3,
    ) -> List[Tuple[int, int]]:
        """
        Generate points along a Bezier curve between start and end.

        Args:
            start: Starting point (x, y)
            end: Ending point (x, y)
            steps: Number of points to generate
            curvature: How curved the path should be (0-1)

        Returns:
            List of (x, y) points along the curve
        """
        # Add some randomness to curvature
        curvature = curvature * (0.8 + random.random() * 0.4)

        # Generate control points for cubic Bezier
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.sqrt(dx * dx + dy * dy)

        # Control point offset perpendicular to the line
        offset = distance * curvature * (1 if random.random() > 0.5 else -1)

        # Calculate perpendicular direction
        if distance > 0:
            perp_x = -dy / distance
            perp_y = dx / distance
        else:
            perp_x, perp_y = 0, 1

        # Control points at 1/3 and 2/3 of the way
        cp1 = (
            start[0] + dx * 0.33 + perp_x * offset * random.uniform(0.5, 1.5),
            start[1] + dy * 0.33 + perp_y * offset * random.uniform(0.5, 1.5),
        )
        cp2 = (
            start[0] + dx * 0.67 + perp_x * offset * random.uniform(-0.5, 0.5),
            start[1] + dy * 0.67 + perp_y * offset * random.uniform(-0.5, 0.5),
        )

        # Generate points along the curve
        points = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier formula
            x = (
                (1 - t) ** 3 * start[0]
                + 3 * (1 - t) ** 2 * t * cp1[0]
                + 3 * (1 - t) * t ** 2 * cp2[0]
                + t ** 3 * end[0]
            )
            y = (
                (1 - t) ** 3 * start[1]
                + 3 * (1 - t) ** 2 * t * cp1[1]
                + 3 * (1 - t) * t ** 2 * cp2[1]
                + t ** 3 * end[1]
            )
            points.append((int(x), int(y)))

        return points

    @staticmethod
    def generate_movement_delays(
        steps: int,
        base_delay_ms: float = 5,
        variance: float = 0.5,
    ) -> List[float]:
        """
        Generate delays between mouse movement steps.

        Humans slow down at the start and end of movements.

        Args:
            steps: Number of steps
            base_delay_ms: Base delay between steps in milliseconds
            variance: Random variance factor (0-1)

        Returns:
            List of delays in milliseconds
        """
        delays = []
        for i in range(steps):
            # Progress through movement (0 to 1)
            t = i / steps if steps > 0 else 0

            # Ease-in-out: slower at start and end
            # Using smoothstep function
            ease = t * t * (3 - 2 * t)

            # Combine with inverse to get slower at ends
            speed_factor = 0.5 + abs(0.5 - ease)

            # Apply variance
            delay = base_delay_ms * speed_factor * (1 + (random.random() - 0.5) * variance)
            delays.append(max(1, delay))

        return delays


class HumanTyping:
    """Simulate human-like typing patterns.

    Humans don't type at constant speeds. This class models:
    - Variable inter-key delays based on character pairs
    - Slower typing for special characters
    - Occasional pauses (as if thinking)
    """

    # Base delay between keystrokes (ms)
    BASE_DELAY = 80

    # Character type multipliers
    CHAR_MULTIPLIERS = {
        "space": 1.2,       # Slightly slower after words
        "uppercase": 1.3,   # Need to hold shift
        "punctuation": 1.5, # End of sentence pause
        "number": 1.1,      # Slightly slower for numbers
    }

    # Common digraphs that are typed faster (muscle memory)
    FAST_DIGRAPHS = {
        "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
        "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
        "st", "to", "nt", "ng", "se", "ha", "as", "ou", "io", "le",
        "ve", "co", "me", "de", "hi", "ri", "ro", "ic", "ne", "ea",
    }

    @classmethod
    def get_inter_key_delay(
        cls,
        char: str,
        prev_char: str = "",
        intensity: float = 1.0,
    ) -> float:
        """
        Calculate delay before typing a character.

        Args:
            char: Character about to be typed
            prev_char: Previously typed character
            intensity: Behavior intensity multiplier (0.5 to 2.0)

        Returns:
            Delay in milliseconds
        """
        # Start with base delay
        delay = cls.BASE_DELAY

        # Apply character type multipliers
        if char == " ":
            delay *= cls.CHAR_MULTIPLIERS["space"]
        elif char.isupper():
            delay *= cls.CHAR_MULTIPLIERS["uppercase"]
        elif char in ".,!?;:":
            delay *= cls.CHAR_MULTIPLIERS["punctuation"]
        elif char.isdigit():
            delay *= cls.CHAR_MULTIPLIERS["number"]

        # Fast digraphs
        digraph = (prev_char + char).lower()
        if digraph in cls.FAST_DIGRAPHS:
            delay *= 0.7  # Faster for common pairs

        # Add Gaussian variance
        variance = delay * 0.3
        delay = max(20, delay + random.gauss(0, variance))

        # Occasional thinking pause (1% chance)
        if random.random() < 0.01:
            delay += random.uniform(200, 500)

        # Apply intensity
        delay *= intensity

        return delay

    @classmethod
    async def type_text(
        cls,
        page: Any,
        selector: str,
        text: str,
        intensity: float = 1.0,
    ) -> None:
        """
        Type text with human-like timing.

        Args:
            page: Playwright/browser page object
            selector: Element selector to type into
            text: Text to type
            intensity: Behavior intensity multiplier
        """
        await page.click(selector)
        await asyncio.sleep(0.1 * intensity)  # Small pause after click

        prev_char = ""
        for char in text:
            delay = cls.get_inter_key_delay(char, prev_char, intensity)
            await asyncio.sleep(delay / 1000)  # Convert to seconds
            await page.keyboard.type(char)
            prev_char = char


class ReadingBehavior:
    """Simulate human reading patterns.

    Humans need time to read content. Immediate extraction
    after page load is a bot indicator.
    """

    # Average reading speed (words per minute)
    WPM = 250

    # Average word length in characters
    CHARS_PER_WORD = 5

    @classmethod
    def calculate_read_time(
        cls,
        content_length: int,
        has_images: bool = False,
        intensity: float = 1.0,
    ) -> float:
        """
        Calculate realistic reading time for content.

        Args:
            content_length: Content length in characters
            has_images: Whether content contains images (adds viewing time)
            intensity: Behavior intensity multiplier

        Returns:
            Reading time in seconds
        """
        # Estimate word count
        words = content_length / cls.CHARS_PER_WORD

        # Base reading time
        minutes = words / cls.WPM
        seconds = minutes * 60

        # Add time for images (2-4 seconds each, estimate based on content)
        if has_images:
            estimated_images = max(1, content_length // 3000)  # Rough estimate
            seconds += estimated_images * random.uniform(2, 4)

        # Add variance
        variance = seconds * 0.2
        seconds = max(0.5, seconds + random.gauss(0, variance))

        # Apply intensity (higher = longer pauses)
        seconds *= intensity

        # Cap at reasonable maximum
        return min(seconds, 30)

    @classmethod
    def calculate_scroll_pause(
        cls,
        scroll_distance: int,
        intensity: float = 1.0,
    ) -> float:
        """
        Calculate pause time after scrolling.

        Args:
            scroll_distance: Distance scrolled in pixels
            intensity: Behavior intensity multiplier

        Returns:
            Pause time in seconds
        """
        # Base pause proportional to scroll distance
        base_pause = (scroll_distance / 500) * 0.5

        # Add variance
        pause = max(0.2, base_pause + random.uniform(-0.2, 0.3))

        # Apply intensity
        return pause * intensity


class HumanBehavior:
    """Orchestrator for human-like browser behavior.

    Combines all behavioral simulation components for
    realistic automation that evades detection.
    """

    def __init__(self, intensity: float = 1.0):
        """
        Initialize behavior orchestrator.

        Args:
            intensity: Overall behavior intensity (0.5 to 2.0)
                      - 0.5: Faster, less human-like
                      - 1.0: Normal human behavior
                      - 2.0: Slower, very deliberate
        """
        self.intensity = max(0.5, min(2.0, intensity))
        self.bezier = BezierCurve()
        self.typing = HumanTyping()
        self.reading = ReadingBehavior()

    async def move_to_element(
        self,
        page: Any,
        selector: str,
        click: bool = False,
    ) -> None:
        """
        Move mouse to element with natural curve.

        Args:
            page: Playwright/browser page object
            selector: Target element selector
            click: Whether to click after moving
        """
        # Get current mouse position (or use viewport center as start)
        try:
            current_pos = await page.evaluate("({x: window.mouseX || 500, y: window.mouseY || 300})")
            start = (current_pos.get("x", 500), current_pos.get("y", 300))
        except Exception:
            start = (500, 300)

        # Get target element position
        try:
            box = await page.locator(selector).bounding_box()
            if not box:
                # Fallback to direct click if can't get position
                if click:
                    await page.click(selector)
                return

            # Target center of element with small random offset
            end = (
                int(box["x"] + box["width"] / 2 + random.uniform(-5, 5)),
                int(box["y"] + box["height"] / 2 + random.uniform(-5, 5)),
            )
        except Exception:
            if click:
                await page.click(selector)
            return

        # Generate movement path
        steps = max(20, int(math.sqrt((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) / 10))
        points = self.bezier.generate_points(start, end, steps)
        delays = self.bezier.generate_movement_delays(steps, base_delay_ms=5 * self.intensity)

        # Execute movement
        for point, delay in zip(points, delays):
            await page.mouse.move(point[0], point[1])
            await asyncio.sleep(delay / 1000)

        # Click if requested
        if click:
            await asyncio.sleep(random.uniform(0.05, 0.15) * self.intensity)
            await page.mouse.click(end[0], end[1])

    async def human_type(
        self,
        page: Any,
        selector: str,
        text: str,
        clear_first: bool = True,
    ) -> None:
        """
        Type text with human-like timing.

        Args:
            page: Playwright/browser page object
            selector: Input element selector
            text: Text to type
            clear_first: Whether to clear existing content first
        """
        # Move to element first
        await self.move_to_element(page, selector, click=True)

        await asyncio.sleep(random.uniform(0.1, 0.3) * self.intensity)

        # Clear if requested
        if clear_first:
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.05)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.1)

        # Type with human timing
        await self.typing.type_text(page, selector, text, self.intensity)

    async def reading_pause(
        self,
        content_length: int,
        has_images: bool = False,
        max_pause: float = 10.0,
    ) -> None:
        """
        Pause to simulate reading content.

        Args:
            content_length: Content length in characters
            has_images: Whether content contains images
            max_pause: Maximum pause time in seconds
        """
        pause = self.reading.calculate_read_time(
            content_length,
            has_images,
            self.intensity,
        )
        pause = min(pause, max_pause)
        await asyncio.sleep(pause)

    async def scroll_pause(
        self,
        scroll_distance: int,
    ) -> None:
        """
        Pause after scrolling to simulate reading.

        Args:
            scroll_distance: Distance scrolled in pixels
        """
        pause = self.reading.calculate_scroll_pause(scroll_distance, self.intensity)
        await asyncio.sleep(pause)

    async def random_micro_movement(
        self,
        page: Any,
    ) -> None:
        """
        Perform small random mouse movement.

        Humans rarely keep the mouse perfectly still.

        Args:
            page: Playwright/browser page object
        """
        try:
            current = await page.evaluate("({x: window.mouseX || 500, y: window.mouseY || 300})")
            x = current.get("x", 500) + random.randint(-30, 30)
            y = current.get("y", 300) + random.randint(-30, 30)
            await page.mouse.move(x, y)
        except Exception:
            pass

    async def natural_wait(
        self,
        min_seconds: float = 0.5,
        max_seconds: float = 2.0,
    ) -> None:
        """
        Wait for a natural random duration.

        Args:
            min_seconds: Minimum wait time
            max_seconds: Maximum wait time
        """
        wait = random.uniform(min_seconds, max_seconds) * self.intensity
        await asyncio.sleep(wait)
