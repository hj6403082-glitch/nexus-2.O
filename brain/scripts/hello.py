"""Say hello to someone (an example; safe to delete)."""

import sys

name = " ".join(sys.argv[1:]) or "Boss"
print(f"Hello, {name}!")
