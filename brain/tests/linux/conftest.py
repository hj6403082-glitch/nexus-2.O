"""Linux toolset tests. Most use fakes and run on any OS; see each module's skips."""

import importlib.util

# dbus-fast is installed on Linux only; without it this module can't even be imported.
collect_ignore = [] if importlib.util.find_spec("dbus_fast") else ["test_dbus_integration.py"]
