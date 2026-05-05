---
trigger: always_on
---

CODING STANDARD:

- Use type hints
- Use logging module
- No print() statements
- Use pathlib instead of os.path where possible
- All functions must have docstrings
- Handle 401 token refresh properly

PROJECT RULES:

1. Never use os.getcwd().
2. Always derive PROJECT_ROOT from __file__.
3. All outputs must go to /results.
4. All intermediate SNAP outputs must go to /data/output_int.
5. Never hardcode credentials.
6. Always preserve relative orbit consistency.
7. Do not remove temporal baseline checks.
8. Do not simplify interferometric processing logic.
9. Always log to /logs.
10. Never change file structure without explicit instruction.
