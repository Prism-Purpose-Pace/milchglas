"""Suite-wide setup: Hypothesis profiles.

`dev` runs locally, `ci` on CI runners (GitHub sets CI): more examples, derandomized so a
failing example reproduces from the printed blob. HYPOTHESIS_PROFILE overrides either.
"""

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=100, deadline=None)
settings.register_profile("ci", max_examples=500, deadline=None, derandomize=True, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci" if os.environ.get("CI") else "dev"))
