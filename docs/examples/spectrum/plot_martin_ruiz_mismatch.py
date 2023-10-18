"""
N. Martin & J. M. Ruiz Spectral Mismatch Modifier
=================================================

How to use this correction factor to adjust the POA global irradiance.
"""

# %%
# Effectiveness of a material to convert incident sunlight to current depends
# on the incident light wavelength. During the day, the spectral distribution
# of the incident irradiance varies from the standard testing spectra,
# introducing a small difference between the expected and the real output.
# In [1]_, N. Martín and J. M. Ruiz propose 3 mismatch factors, one for each
# irradiance component. These mismatch modifiers are calculated with the help
# of the airmass, the clearness index and three experimental fitting
# parameters. In the same paper, these parameters have been obtained for m-Si,
# p-Si and a-Si modules.
# With :py:func:`pvlib.spectrum.martin_ruiz` we are able to make use of these
# already computed values or provide ours.
#
# References
# ----------
#  .. [1] Martín, N. and Ruiz, J.M. (1999), A new method for the spectral
#     characterisation of PV modules. Prog. Photovolt: Res. Appl., 7: 299-310.
#     :doi:`10.1002/(SICI)1099-159X(199907/08)7:4<299::AID-PIP260>3.0.CO;2-0`
#
# Calculating the incident and modified global irradiance
# -------------------------------------------------------
#
# Mismatch modifiers are applied to the irradiance components, so first
# step is to get them. We define an hypothetical POA surface and use a TMY to
# compute sky diffuse, ground reflected and direct irradiances.

import os

import matplotlib.pyplot as plt
import pvlib
from scipy import stats
import pandas as pd

surface_tilt = 40
surface_azimuth = 180  # Pointing South

# Get TMY data & create location
datapath = os.path.join(
    pvlib.__path__[0], "data", "tmy_45.000_8.000_2005_2016.csv"
)
pvgis_data, _, metadata, _ = pvlib.iotools.read_pvgis_tmy(
    datapath, map_variables=True
)
site = pvlib.location.Location(
    metadata["latitude"], metadata["longitude"], altitude=metadata["elevation"]
)

# Coerce a year: function above returns typical months of different years
pvgis_data.index = [ts.replace(year=2022) for ts in pvgis_data.index]
# Select days to show
weather_data = pvgis_data["2022-09-03":"2022-09-06"]

# Then calculate all we need to get the irradiance components
solar_pos = site.get_solarposition(weather_data.index)

extra_rad = pvlib.irradiance.get_extra_radiation(weather_data.index)

poa_sky_diffuse = pvlib.irradiance.haydavies(
    surface_tilt,
    surface_azimuth,
    weather_data["dhi"],
    weather_data["dni"],
    extra_rad,
    solar_pos["apparent_zenith"],
    solar_pos["azimuth"],
)

poa_ground_diffuse = pvlib.irradiance.get_ground_diffuse(
    surface_tilt, weather_data["ghi"]
)

aoi = pvlib.irradiance.aoi(
    surface_tilt,
    surface_azimuth,
    solar_pos["apparent_zenith"],
    solar_pos["azimuth"],
)

# Get dataframe with all components and global (includes 'poa_direct')
poa_irrad = pvlib.irradiance.poa_components(
    aoi, weather_data["dni"], poa_sky_diffuse, poa_ground_diffuse
)

# Apply Martin & Ruiz IAM modifiers
iam_direct = pvlib.iam.martin_ruiz(aoi)
iam_sky_diffuse, iam_ground_diffuse = pvlib.iam.martin_ruiz_diffuse(
    surface_tilt
)

poa_irrad["poa_direct"] = poa_irrad["poa_direct"] * iam_direct
poa_irrad["poa_sky_diffuse"] = poa_irrad["poa_sky_diffuse"] * iam_sky_diffuse
poa_irrad["poa_ground_diffuse"] = (
    poa_irrad["poa_ground_diffuse"] * iam_ground_diffuse
)

# %%
# Here come the modifiers. Let's calculate them with the airmass and clearness
# index.
# First, let's find the airmass and the clearness index.
# Little caution: default values for this model were fitted obtaining the
# airmass through the `'kasten1966'` method, which is not used by default.

airmass = site.get_airmass(solar_position=solar_pos, model="kasten1966")
airmass_absolute = airmass["airmass_absolute"]  # We only use absolute airmass
clearness_index = pvlib.irradiance.clearness_index(
    weather_data["ghi"], solar_pos["zenith"], extra_rad
)

# Get the spectral mismatch modifiers
spectral_modifiers = pvlib.spectrum.martin_ruiz(
    clearness_index, airmass_absolute, module_type="monosi"
)

# %%
# And then we can find the 3 modified components of the POA irradiance
# by means of a simple multiplication.
# Note, however, that this does not modify ``poa_global`` nor
# ``poa_diffuse``, so we should update the dataframe afterwards.

poa_irrad_modified = poa_irrad * spectral_modifiers
# Line above is equivalent to:
# poa_irrad_modified = pd.DataFrame()
# for component in ('poa_direct', 'poa_sky_diffuse', 'poa_ground_diffuse'):
#     poa_irrad_modified[component] = (poa_irrad[component]
#                                      * spectral_modifiers[component])

# We want global modified irradiance
poa_irrad_modified["poa_global"] = (
    poa_irrad_modified["poa_direct"]
    + poa_irrad_modified["poa_sky_diffuse"]
    + poa_irrad_modified["poa_ground_diffuse"]
)
# Don't forget to update `'poa_diffuse'` if you want to use it
# poa_irrad_modified['poa_diffuse'] = \
#     (poa_irrad_modified['poa_sky_diffuse']
#      + poa_irrad_modified['poa_ground_diffuse'])

# %%
# Finally, let's plot the incident vs modified global irradiance, and their
# difference.

poa_irrad_global_diff = (
    poa_irrad["poa_global"] - poa_irrad_modified["poa_global"]
)
plt.figure()
datetimes = poa_irrad.index  # common to poa_irrad_*
plt.plot(datetimes, poa_irrad["poa_global"].to_numpy())
plt.plot(datetimes, poa_irrad_modified["poa_global"].to_numpy())
plt.plot(datetimes, poa_irrad_global_diff.to_numpy())
plt.legend(["Incident", "Modified", "Difference"])
plt.ylabel("POA Global irradiance [W/m²]")
plt.grid()
plt.show()

# %%
# Comparison against other models
# -------------------------------
# During the addition of this model, a question arose about its trustworthiness
# so, in order to check the integrity of the implementation, we will
# compare it against :py:func:`pvlib.spectrum.spectral_factor_sapm` and
# :py:func:`pvlib.spectrum.spectral_factor_firstsolar`.
# Former model needs the parameters that characterise a module, but which one?
# We will take the mean of Sandia parameters `'A0', 'A1', 'A2', 'A3', 'A4'` for
# the same material type.
# On the other hand, :py:func:`~pvlib.atmosphere.first_solar` needs the
# precipitable water. We assume the standard spectrum, `1.42 cm`.

# Retrieve modules and select the subset we want to work with the SAPM model
module_type = "mc-Si"  # Equivalent to monosi
sandia_modules = pvlib.pvsystem.retrieve_sam(name="SandiaMod")
modules_subset = sandia_modules.loc[
    :, sandia_modules.loc["Material"] == module_type
]

# Define typical module and get the means of the A0 to A4 parameters
modules_aggregated = pd.DataFrame(index=("mean", "std"))
for param in ("A0", "A1", "A2", "A3", "A4"):
    result, _, _ = stats.mvsdist(modules_subset.loc[param])
    modules_aggregated[param] = result.mean(), result.std()

# Check if 'mean' is a representative value with help of 'std' just in case
print(modules_aggregated)

# Then apply the SAPM model and calculate introduced difference
modifier_sapm_f1 = pvlib.spectrum.spectral_factor_sapm(
    airmass_absolute, modules_aggregated.loc["mean"]
)
poa_irrad_sapm_modified = poa_irrad["poa_global"] * modifier_sapm_f1
poa_irrad_sapm_difference = poa_irrad["poa_global"] - poa_irrad_sapm_modified

# spectrum.spectral_factor_firstsolar model
first_solar_pw = 1.42  # Default for AM1.5 spectrum
modifier_first_solar = pvlib.spectrum.spectral_factor_firstsolar(
    first_solar_pw, airmass_absolute, module_type="monosi"
)
poa_irrad_first_solar_mod = poa_irrad["poa_global"] * modifier_first_solar
poa_irrad_first_solar_diff = (
    poa_irrad["poa_global"] - poa_irrad_first_solar_mod
)

# %%
# Plot global irradiance difference over time
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
datetimes = poa_irrad_global_diff.index  # common to poa_irrad_*_diff*
plt.figure()
plt.plot(
    datetimes, poa_irrad_global_diff.to_numpy(), label="spectrum.martin_ruiz"
)
plt.plot(
    datetimes,
    poa_irrad_sapm_difference.to_numpy(),
    label="spectrum.spectral_factor_firstsolar",
)
plt.plot(
    datetimes,
    poa_irrad_first_solar_diff.to_numpy(),
    label="pvlib.spectrum.spectral_factor_sapm",
)
plt.legend()
plt.title("Introduced difference comparison of different models")
plt.ylabel("POA Global Irradiance Difference [W/m²]")
plt.grid()
plt.show()

# %%
# Plot modifier vs absolute airmass
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
ama = airmass_absolute.to_numpy()
# spectrum.martin_ruiz has 3 modifiers, so we only calculate one as
# M = S_eff / S_incident that takes into account the global effect
martin_ruiz_agg_modifier = (
    poa_irrad_modified["poa_global"] / poa_irrad["poa_global"]
)
plt.figure()
plt.scatter(
    ama, martin_ruiz_agg_modifier.to_numpy(), label="spectrum.martin_ruiz"
)
plt.scatter(
    ama,
    modifier_sapm_f1.to_numpy(),
    label="pvlib.spectrum.spectral_factor_sapm",
)
plt.scatter(
    ama,
    modifier_first_solar.to_numpy(),
    label="spectrum.spectral_factor_firstsolar",
)
plt.legend()
plt.title("Introduced difference comparison of different models")
plt.xlabel("Absolute airmass")
plt.ylabel(r"Modifier $M = \frac{S_{effective}}{S_{incident}}$")
plt.grid()
plt.show()
