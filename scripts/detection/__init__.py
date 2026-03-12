"""Site detection and profiling."""
# Import directly:
#   from detection.mode_detector import ModeDetector, ScrapeProfile
#   from detection.paywall_detector import PaywallDetector, AccessRestriction

# Shared tracker/fingerprinter patterns for CDP network interception.
# Used by Tiers 2, 2.5, and 3 to block tracking scripts.
# Consolidated from browser-use + tier2_5_agentbrowser patterns.
TRACKER_PATTERNS = [
    # Google Analytics / Tag Manager
    "**/analytics.js",
    "**/gtag/js*",
    "**/ga.js",
    "**/google-analytics.com/**",
    "**/googletagmanager.com/**",
    # Ad networks
    "**/googlesyndication.com/**",
    "**/doubleclick.net/**",
    "**/connect.facebook.net/**",
    # Fingerprinting / Tracking
    "**/fingerprint*.js",
    "**/fp.js",
    "**/tracking*.js",
    "**/pixel*.js",
    "**/beacon*.js",
    "**/collect*",
    # Session replay / Heatmaps
    "**/clarity.js",
    "**/hotjar*.js",
    "**/hj-*.js",
    "**/fullstory*.js",
    "**/mouseflow*.js",
    # Analytics SDKs
    "**/cdn.segment.com/**",
    "**/cdn.amplitude.com/**",
    "**/cdn.mxpnl.com/**",
    "**/_vercel/insights/**",
    # Error tracking
    "**/sentry.io/**",
    "**/browser-intake-datadoghq.com/**",
]
