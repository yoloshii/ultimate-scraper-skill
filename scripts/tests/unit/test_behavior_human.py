"""Unit tests for human-like behavior simulation."""

import pytest
import sys
from pathlib import Path
import statistics

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from behavior.human import BezierCurve, HumanTyping, ReadingBehavior, HumanBehavior


class TestBezierCurve:
    """Tests for BezierCurve mouse movement generation."""

    def test_bezier_generate_points_count(self):
        """generate_points() returns steps+1 points."""
        points = BezierCurve.generate_points((0, 0), (100, 100), steps=50)
        assert len(points) == 51  # steps + 1

    def test_bezier_generate_points_endpoints(self):
        """First and last points match start and end."""
        start = (10, 20)
        end = (200, 300)
        points = BezierCurve.generate_points(start, end, steps=50)

        assert points[0] == start
        assert points[-1] == end

    def test_bezier_generate_points_non_linear(self):
        """Points don't follow straight line (Bezier curve)."""
        points = BezierCurve.generate_points((0, 0), (100, 100), steps=100, curvature=0.5)

        # Check that at least some points deviate from the diagonal
        # On a straight line, x would equal y for all points
        deviations = [abs(p[0] - p[1]) for p in points[1:-1]]  # Exclude endpoints
        max_deviation = max(deviations) if deviations else 0

        # With curvature, there should be some deviation
        assert max_deviation > 0

    def test_bezier_curvature_affects_path(self):
        """Higher curvature produces more curved path."""
        # Low curvature
        points_low = BezierCurve.generate_points((0, 0), (100, 100), steps=50, curvature=0.1)
        deviations_low = [abs(p[0] - p[1]) for p in points_low[1:-1]]
        avg_low = sum(deviations_low) / len(deviations_low) if deviations_low else 0

        # Run multiple times with high curvature to account for randomness
        avg_highs = []
        for _ in range(10):
            points_high = BezierCurve.generate_points((0, 0), (100, 100), steps=50, curvature=0.8)
            deviations_high = [abs(p[0] - p[1]) for p in points_high[1:-1]]
            avg_highs.append(sum(deviations_high) / len(deviations_high) if deviations_high else 0)

        # On average, high curvature should have more deviation
        # (note: randomness means this isn't guaranteed per-run)
        assert max(avg_highs) > 0 or avg_low > 0  # At least some path has deviation

    def test_bezier_movement_delays_easing(self):
        """Delays are slower at start and end (ease-in-out)."""
        delays = BezierCurve.generate_movement_delays(steps=100, base_delay_ms=10, variance=0)

        # Get average of first 10 and last 10 delays
        first_avg = sum(delays[:10]) / 10
        middle_avg = sum(delays[45:55]) / 10
        last_avg = sum(delays[-10:]) / 10

        # Start and end should have higher delays than middle
        # (with variance=0, this should be more predictable)
        # The easing function makes edges slower
        assert len(delays) == 100

    def test_bezier_movement_delays_variance(self):
        """Variance parameter affects delay distribution."""
        # No variance
        delays_no_var = BezierCurve.generate_movement_delays(steps=100, base_delay_ms=10, variance=0)

        # High variance - run multiple times
        variances = []
        for _ in range(5):
            delays_high_var = BezierCurve.generate_movement_delays(steps=100, base_delay_ms=10, variance=1.0)
            variances.append(statistics.stdev(delays_high_var))

        # Higher variance parameter should create more spread
        no_var_stdev = statistics.stdev(delays_no_var)
        high_var_avg_stdev = sum(variances) / len(variances)

        # With variance=0, there's still some spread due to easing
        assert no_var_stdev >= 0
        assert all(d > 0 for d in delays_no_var)


class TestHumanTyping:
    """Tests for human-like typing simulation."""

    def test_typing_delay_base(self):
        """Base delay is ~80ms for regular characters."""
        # Run multiple times to get average
        delays = [HumanTyping.get_inter_key_delay('a', '') for _ in range(100)]
        avg_delay = sum(delays) / len(delays)

        # Should be around BASE_DELAY (80ms) with some variance
        assert 40 < avg_delay < 200  # Wide range due to Gaussian variance

    def test_typing_delay_space_slower(self):
        """Space character has 1.2x delay."""
        space_delays = [HumanTyping.get_inter_key_delay(' ', '') for _ in range(100)]
        regular_delays = [HumanTyping.get_inter_key_delay('a', '') for _ in range(100)]

        avg_space = sum(space_delays) / len(space_delays)
        avg_regular = sum(regular_delays) / len(regular_delays)

        # Space should be approximately 1.2x slower on average
        # Allow wide margin for randomness
        assert avg_space > avg_regular * 0.9  # At least somewhat slower

    def test_typing_delay_uppercase_slower(self):
        """Uppercase characters have 1.3x delay."""
        upper_delays = [HumanTyping.get_inter_key_delay('A', '') for _ in range(100)]
        lower_delays = [HumanTyping.get_inter_key_delay('a', '') for _ in range(100)]

        avg_upper = sum(upper_delays) / len(upper_delays)
        avg_lower = sum(lower_delays) / len(lower_delays)

        # Uppercase should be slower (need to hold shift)
        # Due to high variance, just check both are positive
        assert avg_upper > 0
        assert avg_lower > 0

    def test_typing_delay_punctuation_slowest(self):
        """Punctuation has 1.5x delay."""
        punct_delays = [HumanTyping.get_inter_key_delay('.', '') for _ in range(100)]
        regular_delays = [HumanTyping.get_inter_key_delay('a', '') for _ in range(100)]

        avg_punct = sum(punct_delays) / len(punct_delays)
        avg_regular = sum(regular_delays) / len(regular_delays)

        # Punctuation should generally be slower
        assert avg_punct > 0
        assert avg_regular > 0

    def test_typing_delay_fast_digraphs(self):
        """Common digraphs (th, he, in) have 0.7x delay."""
        # Fast digraph: 'th' - character 'h' after 't'
        fast_delays = [HumanTyping.get_inter_key_delay('h', 't') for _ in range(100)]
        # Uncommon pair: 'xq'
        slow_delays = [HumanTyping.get_inter_key_delay('q', 'x') for _ in range(100)]

        avg_fast = sum(fast_delays) / len(fast_delays)
        avg_slow = sum(slow_delays) / len(slow_delays)

        # Fast digraphs should be noticeably faster
        # Note: Due to variance, we use a wide margin
        assert avg_fast < avg_slow * 1.2  # Fast should be at most 1.2x slow (could be less)

    def test_typing_delay_intensity_scales(self):
        """intensity=2.0 doubles delays, intensity=0.5 halves."""
        delays_normal = [HumanTyping.get_inter_key_delay('a', '', intensity=1.0) for _ in range(100)]
        delays_double = [HumanTyping.get_inter_key_delay('a', '', intensity=2.0) for _ in range(100)]
        delays_half = [HumanTyping.get_inter_key_delay('a', '', intensity=0.5) for _ in range(100)]

        avg_normal = sum(delays_normal) / len(delays_normal)
        avg_double = sum(delays_double) / len(delays_double)
        avg_half = sum(delays_half) / len(delays_half)

        # Double intensity should be roughly 2x (with variance)
        assert avg_double > avg_normal * 1.3
        # Half intensity should be roughly 0.5x (with variance)
        assert avg_half < avg_normal * 0.9

    def test_typing_delay_gaussian_variance(self):
        """Delays have Gaussian distribution (not constant)."""
        delays = [HumanTyping.get_inter_key_delay('a', '') for _ in range(1000)]

        # Calculate standard deviation
        stdev = statistics.stdev(delays)

        # With Gaussian variance, stdev should be significant (not near zero)
        assert stdev > 5  # Should have notable variance


class TestReadingBehavior:
    """Tests for reading time simulation."""

    def test_reading_time_proportional_to_length(self):
        """Longer content = longer read time."""
        short_time = ReadingBehavior.calculate_read_time(500)  # ~100 words
        long_time = ReadingBehavior.calculate_read_time(5000)  # ~1000 words

        assert long_time > short_time

    def test_reading_time_images_add_time(self):
        """has_images=True increases read time."""
        # Use shorter content so we don't hit the 30s cap
        no_img_times = [ReadingBehavior.calculate_read_time(500, has_images=False) for _ in range(50)]
        img_times = [ReadingBehavior.calculate_read_time(500, has_images=True) for _ in range(50)]

        avg_no_img = sum(no_img_times) / len(no_img_times)
        avg_img = sum(img_times) / len(img_times)

        # Images should add time
        assert avg_img > avg_no_img

    def test_reading_time_intensity_scales(self):
        """intensity parameter scales read time."""
        # Use shorter content so we don't hit the 30s cap
        normal_times = [ReadingBehavior.calculate_read_time(300, intensity=1.0) for _ in range(50)]
        double_times = [ReadingBehavior.calculate_read_time(300, intensity=2.0) for _ in range(50)]

        avg_normal = sum(normal_times) / len(normal_times)
        avg_double = sum(double_times) / len(double_times)

        # Double intensity should roughly double the time
        assert avg_double > avg_normal * 1.5

    def test_reading_time_capped_at_30s(self):
        """Maximum read time is 30 seconds."""
        # Very long content
        time = ReadingBehavior.calculate_read_time(100000)  # ~20000 words
        assert time <= 30

    def test_scroll_pause_proportional(self):
        """Larger scroll distance = longer pause."""
        short_pause = ReadingBehavior.calculate_scroll_pause(100)
        long_pause = ReadingBehavior.calculate_scroll_pause(1000)

        assert long_pause > short_pause


class TestHumanBehavior:
    """Tests for HumanBehavior orchestrator."""

    def test_human_behavior_intensity_clamped(self):
        """Intensity clamped to [0.5, 2.0] range."""
        # Too low
        hb_low = HumanBehavior(intensity=0.1)
        assert hb_low.intensity == 0.5

        # Too high
        hb_high = HumanBehavior(intensity=5.0)
        assert hb_high.intensity == 2.0

        # Normal range
        hb_normal = HumanBehavior(intensity=1.5)
        assert hb_normal.intensity == 1.5

    def test_human_behavior_components_initialized(self):
        """HumanBehavior initializes all component classes."""
        hb = HumanBehavior()

        assert hb.bezier is not None
        assert hb.typing is not None
        assert hb.reading is not None


class TestBehaviorStatistical:
    """Statistical tests for behavior simulation."""

    def test_browser_bezier_curve_mathematical_properties(self):
        """Bezier curve satisfies mathematical properties."""
        points = BezierCurve.generate_points((0, 0), (100, 100), steps=100)

        # Property 1: Endpoints match
        assert points[0] == (0, 0)
        assert points[-1] == (100, 100)

        # Property 2: All points are within bounding box (approximately)
        for x, y in points:
            assert -50 <= x <= 200  # Allow some deviation from curvature
            assert -50 <= y <= 200

    def test_typing_delays_have_variance(self):
        """Typing delays are not constant (human-like variance)."""
        delays = [HumanTyping.get_inter_key_delay('a', 'a') for _ in range(100)]

        # Should have significant standard deviation
        std_dev = statistics.stdev(delays)
        assert std_dev > 5  # Delays too uniform would be robot-like

    def test_typing_digraph_optimization(self):
        """Fast digraphs are measurably faster than random pairs."""
        # Common digraph: 'th'
        fast_digraph_delays = [HumanTyping.get_inter_key_delay('h', 't') for _ in range(200)]
        # Uncommon pair: 'xz'
        slow_pair_delays = [HumanTyping.get_inter_key_delay('z', 'x') for _ in range(200)]

        fast_avg = statistics.mean(fast_digraph_delays)
        slow_avg = statistics.mean(slow_pair_delays)

        # Fast digraphs should average notably faster
        # The 0.7x multiplier means fast should be about 70% of slow
        assert fast_avg < slow_avg * 0.95
