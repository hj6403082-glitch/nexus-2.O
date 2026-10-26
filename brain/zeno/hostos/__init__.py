"""Back ends for the machine Zeno runs on.

``linux/`` and ``windows/`` never import each other; the shared parts live here.
``zeno.agent.tools.os_loader`` picks one at boot with ``platform.system()``.
"""
