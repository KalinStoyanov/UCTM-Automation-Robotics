"""Compatibility alias for the canonical DD-M2 controller.

Implementation: core.control.remote_control
"""

import sys
from core.control import remote_control as controller

sys.modules[__name__] = controller
