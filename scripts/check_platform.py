import os

import pytest

from axiom.settings import Settings

os.environ["AXIOM_TEST_DATABASE_URL"] = Settings().database_url
raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider"]))
