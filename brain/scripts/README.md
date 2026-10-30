# Owner scripts

Zeno's agent can run the Python scripts in this folder, by name, and only after you
approve each run. It cannot write, edit or run anything else.

- One script per `.py` file. The file name (without `.py`) is the name Zeno uses:
  lowercase letters, digits, `-` and `_`.
- The first line of the module docstring is the description Zeno reads, so make it
  say what the script does.
- Arguments arrive as plain strings in `sys.argv[1:]` (at most 10, no shell).
- Scripts run with the brain's Python in isolated mode (`python -I`), in this
  folder, with a minimal environment, `ZENO_SCRIPT_TIMEOUT` seconds (30) and the
  first `ZENO_SCRIPT_MAX_OUTPUT` characters (4000) of output kept.

Only put scripts here that you would be happy to run yourself.
