# -----------------------
# tests/state_integrity/check_darts_params.py
# -----------------------
# Quick diagnostic script - run this to see what parameter your Darts accepts
import inspect
from darts.models import NBEATSModel

sig = inspect.signature(NBEATSModel.__init__)
print("NBEATSModel.__init__ parameters:")
for param_name in sig.parameters.keys():
    print(f"  - {param_name}")

print("\nLooking for trainer-related parameters:")
for param_name in sig.parameters.keys():
    if 'trainer' in param_name.lower():
        print(f"  FOUND: {param_name}")