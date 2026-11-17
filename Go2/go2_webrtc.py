"""Compatibility alias for the canonical DD-M2 WebRTC adapter."""

import sys
from core.communication import go2_webrtc as adapter

sys.modules[__name__] = adapter
