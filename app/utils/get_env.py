# app/utils/get_env.py

import os

def get_bool_env(var_name, default=False):
    value = os.getenv(var_name)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on", "y")