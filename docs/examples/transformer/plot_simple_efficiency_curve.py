"""
Simple transformer model
========================

This example shows the usage of :py:func:`~pvlib.transformer.simple_efficiency`.
"""

# %%
from pvlib.transformer import simple_efficiency
import matplotlib.pyplot as plt
import numpy as np

# %%
# Transformer modelling with :py:func:`pvlib.transformer.simple_efficiency`
# splits power losses into two different effects: constant (no load) power
# losses (in the transformer core, mainly due to eddy currents), and a load
# losses factor that is multiplied by power squared (for a fixed input and
# output voltages this is related to the current through the windings, and it
# mainly represents their heating in the due to the Joule effect).
# Equations may be found at the function docstring.
#
# This transformer modelling is widely used in the industry. Standard IEC
# 60076-1 uses this model to describe high power transformers used in power
# distribution grids, for example.
#
# Utility scale solar systems may have power meters installed between the grid
# and the transformers. See the following diagram of the power flux:
#
# PV panels -> Inverters -> Transformer -> Power meters -> Grid
#
# Constant power losses exist as long as the transformer is connected to the
# grid. Load losses will depend on the amount of power going through the
# transformer.
#
# The following cases are based on a 100 kW transformer, with 1% (1 kW)
# constant load losses and 4% (4 kW) load losses at max power.

xformer_nominal_max_power = 100_000  # W
xformer_no_load_losses = 1_000  # W
xformer_load_losses = 4_000  # W
# note simple_efficiency takes the ratio of losses to nominal power
model_kwargs = {
    "transformer_rating": xformer_nominal_max_power,
    "no_load_loss": xformer_no_load_losses / xformer_nominal_max_power,
    "load_loss": xformer_load_losses / xformer_nominal_max_power,
}

# %%
# Case 1: Power is injected to grid
# ---------------------------------
# PV installation is producing electricity. Inverters inject 100 kW into the
# transformer. Given the model parameters, the following model run will
# calculate the output power of the transformer.

case1_pwr = simple_efficiency(100_000, **model_kwargs)
print(case1_pwr)

# Out of the full 100 kW, around 95 kW are making it into the grid.

# %%
# Case 2: No power is injected
# ----------------------------
# At night, no power is being generated nor consumed. How much power is taking
# the transformer?

case2_pwr = simple_efficiency(0, **model_kwargs)
print(case2_pwr)

# In this case, negative power means energy taken from the grid.

# %%
# Case 3: Power is consumed
# -------------------------
# There is a load connected left to the transformer. It is using full nominal
# power, 100 kW (e.g. a building is connected to it). How much power does the
# power meter measure?

case3_pwr = simple_efficiency(-100_000, **model_kwargs)
print(case3_pwr)

# As expected, power taken from the grid is higher since you must add in the
# losses dissipated by the transformer itself.

# %%
# General behaviour of the transformer
# ------------------------------------
# The following plot shows the output power (in this example, flowing into the
# grid), with respect to the input power (the one injected into the
# transformer). Positive means power direction is into grid, negative means
# it is drawn from it.

input_power_vec = np.linspace(
    -xformer_nominal_max_power, xformer_nominal_max_power, 1000
)
output_power_modelled_vec = simple_efficiency(input_power_vec, **model_kwargs)

plt.suptitle("Output power of the transformer as a function of input power")
plt.title(
    f"Nominal power={xformer_nominal_max_power:_}, No load loss={model_kwargs['no_load_loss']:.1%}, "
    f"Load loss={model_kwargs['load_loss']:.1%}"
)
plt.plot(input_power_vec, output_power_modelled_vec)
plt.grid()
plt.show()

# %%
# Exaggerated example
# -------------------
# 1 kW transformer, 10 % no load losses and 20 % load losses

nominal_pwr = 1_000  # W
no_load_losses = 0.10  # %
load_losses = 0.20  # %

input_power_vec = np.linspace(
    -nominal_pwr, nominal_pwr, 1000
)
output_power_modelled_vec = simple_efficiency(input_power_vec, no_load_losses, 0.20, nominal_pwr)

plt.suptitle("Output power of the transformer as a function of input power")
plt.title(
    f"Nominal power={nominal_pwr:_}, No load loss={no_load_losses:.1%}, "
    f"Load loss={load_losses:.1%}"
)
plt.plot(input_power_vec, output_power_modelled_vec)
plt.grid()
plt.show()
# %%
