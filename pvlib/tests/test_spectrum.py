import pytest
from numpy.testing import assert_allclose, assert_approx_equal, assert_equal
import pandas as pd
import numpy as np
from pvlib import spectrum
from pvlib._deprecation import pvlibDeprecationWarning

from .conftest import DATA_DIR, assert_series_equal, fail_on_pvlib_version

SPECTRL2_TEST_DATA = DATA_DIR / 'spectrl2_example_spectra.csv'


@pytest.fixture
def spectrl2_data():
    # reference spectra generated with solar_utils==0.3
    """
    expected = solar_utils.spectrl2(
        units=1,
        location=[40, -80, -5],
        datetime=[2020, 3, 15, 10, 45, 59],
        weather=[1013, 15],
        orientation=[0, 180],
        atmospheric_conditions=[1.14, 0.65, 0.344, 0.1, 1.42],
        albedo=[0.3, 0.7, 0.8, 1.3, 2.5, 4.0] + [0.2]*6,
    )
    """
    kwargs = {
        'surface_tilt': 0,
        'relative_airmass': 1.4899535986910446,
        'apparent_zenith': 47.912086486816406,
        'aoi': 47.91208648681641,
        'ground_albedo': 0.2,
        'surface_pressure': 101300,
        'ozone': 0.344,
        'precipitable_water': 1.42,
        'aerosol_turbidity_500nm': 0.1,
        'dayofyear': 75
    }
    df = pd.read_csv(SPECTRL2_TEST_DATA, index_col=0)
    # convert um to nm
    df['wavelength'] = np.round(df['wavelength'] * 1000, 1)
    df[['specdif', 'specdir', 'specetr', 'specglo']] /= 1000
    return kwargs, df


def test_spectrl2(spectrl2_data):
    # compare against output from solar_utils wrapper around NREL spectrl2_2.c
    kwargs, expected = spectrl2_data
    actual = spectrum.spectrl2(**kwargs)
    assert_allclose(expected['wavelength'].values, actual['wavelength'])
    assert_allclose(expected['specdif'].values, actual['dhi'].ravel(),
                    atol=7e-5)
    assert_allclose(expected['specdir'].values, actual['dni'].ravel(),
                    atol=1.5e-4)
    assert_allclose(expected['specetr'], actual['dni_extra'].ravel(),
                    atol=2e-4)
    assert_allclose(expected['specglo'], actual['poa_global'].ravel(),
                    atol=1e-4)


def test_spectrl2_array(spectrl2_data):
    # test that supplying arrays instead of scalars works
    kwargs, expected = spectrl2_data
    kwargs = {k: np.array([v, v, v]) for k, v in kwargs.items()}
    actual = spectrum.spectrl2(**kwargs)

    assert actual['wavelength'].shape == (122,)

    keys = ['dni_extra', 'dhi', 'dni', 'poa_sky_diffuse', 'poa_ground_diffuse',
            'poa_direct', 'poa_global']
    for key in keys:
        assert actual[key].shape == (122, 3)


def test_spectrl2_series(spectrl2_data):
    # test that supplying Series instead of scalars works
    kwargs, expected = spectrl2_data
    kwargs.pop('dayofyear')
    index = pd.to_datetime(['2020-03-15 10:45:59']*3)
    kwargs = {k: pd.Series([v, v, v], index=index) for k, v in kwargs.items()}
    actual = spectrum.spectrl2(**kwargs)

    assert actual['wavelength'].shape == (122,)

    keys = ['dni_extra', 'dhi', 'dni', 'poa_sky_diffuse', 'poa_ground_diffuse',
            'poa_direct', 'poa_global']
    for key in keys:
        assert actual[key].shape == (122, 3)


def test_dayofyear_missing(spectrl2_data):
    # test that not specifying dayofyear with non-pandas inputs raises error
    kwargs, expected = spectrl2_data
    kwargs.pop('dayofyear')
    with pytest.raises(ValueError, match='dayofyear must be specified'):
        _ = spectrum.spectrl2(**kwargs)


def test_aoi_gt_90(spectrl2_data):
    # test that returned irradiance values are non-negative when aoi > 90
    # see GH #1348
    kwargs, _ = spectrl2_data
    kwargs['apparent_zenith'] = 70
    kwargs['aoi'] = 130
    kwargs['surface_tilt'] = 60

    spectra = spectrum.spectrl2(**kwargs)
    for key in ['poa_direct', 'poa_global']:
        message = f'{key} contains negative values for aoi>90'
        assert np.all(spectra[key] >= 0), message


def test_get_example_spectral_response():
    # test that the sample sr is read and interpolated correctly
    sr = spectrum.get_example_spectral_response()
    assert_equal(len(sr), 185)
    assert_equal(np.sum(sr.index), 136900)
    assert_approx_equal(np.sum(sr), 107.6116)

    wavelength = [270, 850, 950, 1200, 4001]
    expected = [0.0, 0.92778, 1.0, 0.0, 0.0]

    sr = spectrum.get_example_spectral_response(wavelength)
    assert_equal(len(sr), len(wavelength))
    assert_allclose(sr, expected, rtol=1e-5)


@fail_on_pvlib_version('0.12')
def test_get_am15g():
    # test that the reference spectrum is read and interpolated correctly
    with pytest.warns(pvlibDeprecationWarning,
                      match="get_reference_spectra instead"):
        e = spectrum.get_am15g()
    assert_equal(len(e), 2002)
    assert_equal(np.sum(e.index), 2761442)
    assert_approx_equal(np.sum(e), 1002.88, significant=6)

    wavelength = [270, 850, 950, 1200, 1201.25, 4001]
    expected = [0.0, 0.893720, 0.147260, 0.448250, 0.4371025, 0.0]

    with pytest.warns(pvlibDeprecationWarning,
                      match="get_reference_spectra instead"):
        e = spectrum.get_am15g(wavelength)
    assert_equal(len(e), len(wavelength))
    assert_allclose(e, expected, rtol=1e-6)


@pytest.mark.parametrize(
    "reference_identifier,expected_sums",
    [
        (
            "ASTM G173-03",  # reference_identifier
            {  # expected_sums
                "extraterrestrial": 1356.15,
                "global": 1002.88,
                "direct": 887.65,
            },
        ),
    ],
)
def test_get_reference_spectra(reference_identifier, expected_sums):
    # test reading of a standard spectrum
    standard = spectrum.get_reference_spectra(standard=reference_identifier)
    assert set(standard.columns) == expected_sums.keys()
    assert standard.index.name == "wavelength"
    assert standard.index.is_monotonic_increasing is True
    expected_sums = pd.Series(expected_sums)  # convert prior to comparison
    assert_series_equal(np.sum(standard, axis=0), expected_sums, atol=1e-2)


def test_get_reference_spectra_custom_wavelengths():
    # test that the spectrum is interpolated correctly when custom wavelengths
    # are specified
    # only checked for ASTM G173-03 reference spectrum
    wavelength = [270, 850, 951.634, 1200, 4001]
    expected_sums = pd.Series(
        {"extraterrestrial": 2.23266, "global": 1.68952, "direct": 1.58480}
    )  # for given ``wavelength``
    standard = spectrum.get_reference_spectra(
        wavelength, standard="ASTM G173-03"
    )
    assert_equal(len(standard), len(wavelength))
    # check no NaN values were returned
    assert not standard.isna().any().any()  # double any to return one value
    assert_series_equal(np.sum(standard, axis=0), expected_sums, atol=1e-4)


def test_get_reference_spectra_invalid_reference():
    # test that an invalid reference identifier raises a ValueError
    with pytest.raises(ValueError, match="Invalid standard identifier"):
        spectrum.get_reference_spectra(standard="invalid")


def test_calc_spectral_mismatch_field(spectrl2_data):
    # test that the mismatch is calculated correctly with
    # - default and custom reference spectrum
    # - single or multiple sun spectra

    # sample data
    _, e_sun = spectrl2_data
    e_sun = e_sun.set_index('wavelength')
    e_sun = e_sun.transpose()

    e_ref = spectrum.get_reference_spectra(standard='ASTM G173-03')["global"]
    sr = spectrum.get_example_spectral_response()

    # test with single sun spectrum, same as ref spectrum
    mm = spectrum.calc_spectral_mismatch_field(sr, e_sun=e_ref)
    assert_approx_equal(mm, 1.0, significant=6)

    # test with single sun spectrum
    mm = spectrum.calc_spectral_mismatch_field(sr, e_sun=e_sun.loc['specglo'])
    assert_approx_equal(mm, 0.992397, significant=6)

    # test with single sun spectrum, also used as reference spectrum
    mm = spectrum.calc_spectral_mismatch_field(sr,
                                               e_sun=e_sun.loc['specglo'],
                                               e_ref=e_sun.loc['specglo'])
    assert_approx_equal(mm, 1.0, significant=6)

    # test with multiple sun spectra
    expected = [0.972982, 0.995581, 0.899782, 0.992397]

    mm = spectrum.calc_spectral_mismatch_field(sr, e_sun=e_sun)
    assert mm.index is e_sun.index
    assert_allclose(mm, expected, rtol=1e-6)


@pytest.fixture
def martin_ruiz_mismatch_data():
    # Data to run tests of spectrum.martin_ruiz
    kwargs = {
        'clearness_index': [0.56, 0.612, 0.664, 0.716, 0.768, 0.82],
        'airmass_absolute': [2, 1.8, 1.6, 1.4, 1.2, 1],
        'monosi_expected': {
            'dir': [1.09149, 1.07275, 1.05432, 1.03622, 1.01842, 1.00093],
            'sky': [0.88636, 0.85009, 0.81530, 0.78194, 0.74994, 0.71925],
            'gnd': [1.02011, 1.00465, 0.98943, 0.97444, 0.95967, 0.94513]},
        'polysi_expected': {
            'dir': [1.09166, 1.07280, 1.05427, 1.03606, 1.01816, 1.00058],
            'sky': [0.89443, 0.85553, 0.81832, 0.78273, 0.74868, 0.71612],
            'gnd': [1.02638, 1.00888, 0.99168, 0.97476, 0.95814, 0.94180]},
        'asi_expected': {
            'dir': [1.07066, 1.05643, 1.04238, 1.02852, 1.01485, 1.00136],
            'sky': [0.94889, 0.91699, 0.88616, 0.85637, 0.82758, 0.79976],
            'gnd': [1.03801, 1.02259, 1.00740, 0.99243, 0.97769, 0.96316]},
        'monosi_model_params_dict': {
            'poa_direct': {'c': 1.029, 'a': -3.13e-1, 'b': 5.24e-3},
            'poa_sky_diffuse': {'c': 0.764, 'a': -8.82e-1, 'b': -2.04e-2},
            'poa_ground_diffuse': {'c': 0.970, 'a': -2.44e-1, 'b': 1.29e-2}},
        'monosi_custom_params_df': pd.DataFrame({
            'poa_direct': [1.029, -0.313, 0.00524],
            'poa_sky_diffuse': [0.764, -0.882, -0.0204]},
            index=('c', 'a', 'b'))
    }
    return kwargs


def test_martin_ruiz_mm_scalar(martin_ruiz_mismatch_data):
    # test scalar input ; only module_type given
    clearness_index = martin_ruiz_mismatch_data['clearness_index'][0]
    airmass_absolute = martin_ruiz_mismatch_data['airmass_absolute'][0]
    result = spectrum.martin_ruiz(clearness_index,
                                  airmass_absolute,
                                  module_type='asi')

    assert_approx_equal(result['poa_direct'],
                        martin_ruiz_mismatch_data['asi_expected']['dir'][0],
                        significant=5)
    assert_approx_equal(result['poa_sky_diffuse'],
                        martin_ruiz_mismatch_data['asi_expected']['sky'][0],
                        significant=5)
    assert_approx_equal(result['poa_ground_diffuse'],
                        martin_ruiz_mismatch_data['asi_expected']['gnd'][0],
                        significant=5)


def test_martin_ruiz_mm_series(martin_ruiz_mismatch_data):
    # test with Series input ; only module_type given
    clearness_index = pd.Series(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = pd.Series(martin_ruiz_mismatch_data['airmass_absolute'])
    expected = pd.DataFrame(data={
        'dir': pd.Series(martin_ruiz_mismatch_data['polysi_expected']['dir']),
        'sky': pd.Series(martin_ruiz_mismatch_data['polysi_expected']['sky']),
        'gnd': pd.Series(martin_ruiz_mismatch_data['polysi_expected']['gnd'])})

    result = spectrum.martin_ruiz(clearness_index, airmass_absolute,
                                  module_type='polysi')
    assert_allclose(result['poa_direct'], expected['dir'], atol=1e-5)
    assert_allclose(result['poa_sky_diffuse'], expected['sky'], atol=1e-5)
    assert_allclose(result['poa_ground_diffuse'], expected['gnd'], atol=1e-5)


def test_martin_ruiz_mm_nans(martin_ruiz_mismatch_data):
    # test NaN in, NaN out ; only module_type given
    clearness_index = pd.Series(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = pd.Series(martin_ruiz_mismatch_data['airmass_absolute'])
    airmass_absolute[:5] = np.nan

    result = spectrum.martin_ruiz(clearness_index, airmass_absolute,
                                  module_type='monosi')
    assert np.isnan(result['poa_direct'][:5]).all()
    assert not np.isnan(result['poa_direct'][5:]).any()
    assert np.isnan(result['poa_sky_diffuse'][:5]).all()
    assert not np.isnan(result['poa_sky_diffuse'][5:]).any()
    assert np.isnan(result['poa_ground_diffuse'][:5]).all()
    assert not np.isnan(result['poa_ground_diffuse'][5:]).any()


def test_martin_ruiz_mm_model_dict(martin_ruiz_mismatch_data):
    # test results when giving 'model_parameters' as dict
    # test custom quantity of components and its names can be given
    clearness_index = pd.Series(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = pd.Series(martin_ruiz_mismatch_data['airmass_absolute'])
    expected = pd.DataFrame(data={
        'dir': pd.Series(martin_ruiz_mismatch_data['monosi_expected']['dir']),
        'sky': pd.Series(martin_ruiz_mismatch_data['monosi_expected']['sky']),
        'gnd': pd.Series(martin_ruiz_mismatch_data['monosi_expected']['gnd'])})
    model_parameters = martin_ruiz_mismatch_data['monosi_model_params_dict']

    result = spectrum.martin_ruiz(
        clearness_index,
        airmass_absolute,
        model_parameters=model_parameters)
    assert_allclose(result['poa_direct'], expected['dir'], atol=1e-5)
    assert_allclose(result['poa_sky_diffuse'], expected['sky'], atol=1e-5)
    assert_allclose(result['poa_ground_diffuse'], expected['gnd'], atol=1e-5)


def test_martin_ruiz_mm_model_df(martin_ruiz_mismatch_data):
    # test results when giving 'model_parameters' as DataFrame
    # test custom quantity of components and its names can be given
    clearness_index = np.array(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = np.array(martin_ruiz_mismatch_data['airmass_absolute'])
    model_parameters = martin_ruiz_mismatch_data['monosi_custom_params_df']
    expected = pd.DataFrame(data={
        'dir': np.array(martin_ruiz_mismatch_data['monosi_expected']['dir']),
        'sky': np.array(martin_ruiz_mismatch_data['monosi_expected']['sky'])})

    result = spectrum.martin_ruiz(
        clearness_index,
        airmass_absolute,
        model_parameters=model_parameters)
    assert_allclose(result['poa_direct'], expected['dir'], atol=1e-5)
    assert_allclose(result['poa_sky_diffuse'], expected['sky'], atol=1e-5)
    assert result['poa_ground_diffuse'].isna().all()


def test_martin_ruiz_mm_error_notimplemented(martin_ruiz_mismatch_data):
    # test exception is raised when module_type does not exist in algorithm
    clearness_index = np.array(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = np.array(martin_ruiz_mismatch_data['airmass_absolute'])

    with pytest.raises(NotImplementedError,
                       match='Cell type parameters not defined in algorithm.'):
        _ = spectrum.martin_ruiz(clearness_index, airmass_absolute,
                                 module_type='')


def test_martin_ruiz_mm_error_model_keys(martin_ruiz_mismatch_data):
    # test exception is raised when  in params keys
    clearness_index = np.array(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = np.array(martin_ruiz_mismatch_data['airmass_absolute'])
    model_parameters = {
        'component_example': {'z': 0.970, 'x': -2.44e-1, 'y': 1.29e-2}}
    with pytest.raises(ValueError,
                       match="You must specify model parameters with keys "
                             "'a','b','c' for each irradiation component."):
        _ = spectrum.martin_ruiz(clearness_index, airmass_absolute,
                                 model_parameters=model_parameters)


def test_martin_ruiz_mm_error_missing_params(martin_ruiz_mismatch_data):
    # test exception is raised when missing module_type and model_parameters
    clearness_index = np.array(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = np.array(martin_ruiz_mismatch_data['airmass_absolute'])

    with pytest.raises(ValueError,
                       match='You must pass at least "module_type" '
                             'or "model_parameters" as arguments.'):
        _ = spectrum.martin_ruiz(clearness_index, airmass_absolute)


def test_martin_ruiz_mm_error_too_many_arguments(martin_ruiz_mismatch_data):
    # test warning is raised with both 'module_type' and 'model_parameters'
    clearness_index = pd.Series(martin_ruiz_mismatch_data['clearness_index'])
    airmass_absolute = pd.Series(martin_ruiz_mismatch_data['airmass_absolute'])
    model_parameters = martin_ruiz_mismatch_data['monosi_model_params_dict']

    with pytest.raises(ValueError,
                       match='Cannot resolve input: must supply only one of '
                             '"module_type" or "model_parameters"'):
        _ = spectrum.martin_ruiz(clearness_index, airmass_absolute,
                                 module_type='asi',
                                 model_parameters=model_parameters)
@pytest.mark.parametrize("module_type,expect", [
    ('cdte', np.array(
        [[0.99051020, 0.97640320, 0.93975028],
         [1.02928735, 1.01881074, 0.98578821],
         [1.04750335, 1.03814456, 1.00623986]])),
    ('monosi', np.array(
        [[0.97769770, 1.02043409, 1.03574032],
         [0.98630905, 1.03055092, 1.04736262],
         [0.98828494, 1.03299036, 1.05026561]])),
    ('polysi', np.array(
        [[0.97704080, 1.01705849, 1.02613202],
         [0.98992828, 1.03173953, 1.04260662],
         [0.99352435, 1.03588785, 1.04730718]])),
    ('cigs', np.array(
        [[0.97459190, 1.02821696, 1.05067895],
         [0.97529378, 1.02967497, 1.05289307],
         [0.97269159, 1.02730558, 1.05075651]])),
    ('asi', np.array(
        [[1.05552750, 0.87707583, 0.72243772],
         [1.11225204, 0.93665901, 0.78487953],
         [1.14555295, 0.97084011, 0.81994083]]))
])
def test_spectral_factor_firstsolar(module_type, expect):
    ams = np.array([1, 3, 5])
    pws = np.array([1, 3, 5])
    ams, pws = np.meshgrid(ams, pws)
    out = spectrum.spectral_factor_firstsolar(pws, ams, module_type)
    assert_allclose(out, expect, atol=0.001)


def test_spectral_factor_firstsolar_supplied():
    # use the cdte coeffs
    coeffs = (0.87102, -0.040543, -0.00929202, 0.10052, 0.073062, -0.0034187)
    out = spectrum.spectral_factor_firstsolar(1, 1, coefficients=coeffs)
    expected = 0.99134828
    assert_allclose(out, expected, atol=1e-3)


def test_spectral_factor_firstsolar_large_airmass_supplied_max():
    # test airmass > user-defined maximum is treated same as airmass=maximum
    m_eq11 = spectrum.spectral_factor_firstsolar(1, 11, 'monosi',
                                                 max_airmass_absolute=11)
    m_gt11 = spectrum.spectral_factor_firstsolar(1, 15, 'monosi',
                                                 max_airmass_absolute=11)
    assert_allclose(m_eq11, m_gt11)


def test_spectral_factor_firstsolar_large_airmass():
    # test that airmass > 10 is treated same as airmass=10
    m_eq10 = spectrum.spectral_factor_firstsolar(1, 10, 'monosi')
    m_gt10 = spectrum.spectral_factor_firstsolar(1, 15, 'monosi')
    assert_allclose(m_eq10, m_gt10)


def test_spectral_factor_firstsolar_ambiguous():
    with pytest.raises(TypeError):
        spectrum.spectral_factor_firstsolar(1, 1)


def test_spectral_factor_firstsolar_ambiguous_both():
    # use the cdte coeffs
    coeffs = (0.87102, -0.040543, -0.00929202, 0.10052, 0.073062, -0.0034187)
    with pytest.raises(TypeError):
        spectrum.spectral_factor_firstsolar(1, 1, 'cdte', coefficients=coeffs)


def test_spectral_factor_firstsolar_low_airmass():
    m_eq58 = spectrum.spectral_factor_firstsolar(1, 0.58, 'monosi')
    m_lt58 = spectrum.spectral_factor_firstsolar(1, 0.1, 'monosi')
    assert_allclose(m_eq58, m_lt58)
    with pytest.warns(UserWarning, match='Low airmass values replaced'):
        _ = spectrum.spectral_factor_firstsolar(1, 0.1, 'monosi')


def test_spectral_factor_firstsolar_range():
    out = spectrum.spectral_factor_firstsolar(np.array([.1, 3, 10]),
                                              np.array([1, 3, 5]),
                                              module_type='monosi')
    expected = np.array([0.96080878, 1.03055092, np.nan])
    assert_allclose(out, expected, atol=1e-3)
    with pytest.warns(UserWarning, match='High precipitable water values '
                      'replaced'):
        out = spectrum.spectral_factor_firstsolar(6, 1.5,
                                                  max_precipitable_water=5,
                                                  module_type='monosi')
    with pytest.warns(UserWarning, match='Low precipitable water values '
                      'replaced'):
        out = spectrum.spectral_factor_firstsolar(np.array([0, 3, 8]),
                                                  np.array([1, 3, 5]),
                                                  module_type='monosi')
    expected = np.array([0.96080878, 1.03055092, 1.04932727])
    assert_allclose(out, expected, atol=1e-3)
    with pytest.warns(UserWarning, match='Low precipitable water values '
                      'replaced'):
        out = spectrum.spectral_factor_firstsolar(0.2, 1.5,
                                                  min_precipitable_water=1,
                                                  module_type='monosi')


@pytest.mark.parametrize('airmass,expected', [
    (1.5, 1.00028714375),
    (np.array([[10, np.nan]]), np.array([[0.999535, 0]])),
    (pd.Series([5]), pd.Series([1.0387675]))
])
def test_spectral_factor_sapm(sapm_module_params, airmass, expected):

    out = spectrum.spectral_factor_sapm(airmass, sapm_module_params)

    if isinstance(airmass, pd.Series):
        assert_series_equal(out, expected, check_less_precise=4)
    else:
        assert_allclose(out, expected, atol=1e-4)


@pytest.mark.parametrize("module_type,expected", [
    ('asi', np.array([0.9108, 0.9897, 0.9707, 1.0265, 1.0798, 0.9537])),
    ('perovskite', np.array([0.9422, 0.9932, 0.9868, 1.0183, 1.0604, 0.9737])),
    ('cdte', np.array([0.9824, 1.0000, 1.0065, 1.0117, 1.042, 0.9979])),
    ('multisi', np.array([0.9907, 0.9979, 1.0203, 1.0081, 1.0058, 1.019])),
    ('monosi', np.array([0.9935, 0.9987, 1.0264, 1.0074, 0.9999, 1.0263])),
    ('cigs', np.array([1.0014, 1.0011, 1.0270, 1.0082, 1.0029, 1.026])),
])
def test_spectral_factor_caballero(module_type, expected):
    ams = np.array([3.0, 1.5, 3.0, 1.5, 1.5, 3.0])
    aods = np.array([1.0, 1.0, 0.02, 0.02, 0.08, 0.08])
    pws = np.array([1.42, 1.42, 1.42, 1.42, 4.0, 1.0])
    out = spectrum.spectral_factor_caballero(pws, ams, aods,
                                             module_type=module_type)
    assert np.allclose(expected, out, atol=1e-3)


def test_spectral_factor_caballero_supplied():
    # use the cdte coeffs
    coeffs = (
        1.0044, 0.0095, -0.0037, 0.0002, 0.0000, -0.0046,
        -0.0182, 0, 0.0095, 0.0068, 0, 1)
    out = spectrum.spectral_factor_caballero(1, 1, 1, coefficients=coeffs)
    expected = 1.0021964
    assert_allclose(out, expected, atol=1e-3)


def test_spectral_factor_caballero_supplied_redundant():
    # Error when specifying both module_type and coefficients
    coeffs = (
        1.0044, 0.0095, -0.0037, 0.0002, 0.0000, -0.0046,
        -0.0182, 0, 0.0095, 0.0068, 0, 1)
    with pytest.raises(ValueError):
        spectrum.spectral_factor_caballero(1, 1, 1, module_type='cdte',
                                           coefficients=coeffs)


def test_spectral_factor_caballero_supplied_ambiguous():
    # Error when specifying neither module_type nor coefficients
    with pytest.raises(ValueError):
        spectrum.spectral_factor_caballero(1, 1, 1, module_type=None,
                                           coefficients=None)


@pytest.mark.parametrize("module_type,expected", [
    ('asi', np.array([1.15534029, 1.1123772, 1.08286684, 1.01915462])),
    ('fs-2', np.array([1.0694323, 1.04948777, 1.03556288, 0.9881471])),
    ('fs-4', np.array([1.05234725, 1.037771, 1.0275516, 0.98820533])),
    ('multisi', np.array([1.03310403, 1.02391703, 1.01744833, 0.97947605])),
    ('monosi', np.array([1.03225083, 1.02335353, 1.01708734, 0.97950110])),
    ('cigs', np.array([1.01475834, 1.01143927, 1.00909094, 0.97852966])),
])
def test_spectral_factor_pvspec(module_type, expected):
    ams = np.array([1.0, 1.5, 2.0, 1.5])
    kcs = np.array([0.4, 0.6, 0.8, 1.4])
    out = spectrum.spectral_factor_pvspec(ams, kcs,
                                          module_type=module_type)
    assert np.allclose(expected, out, atol=1e-8)


@pytest.mark.parametrize("module_type,expected", [
    ('asi', pd.Series([1.15534029, 1.1123772, 1.08286684, 1.01915462])),
    ('fs-2', pd.Series([1.0694323, 1.04948777, 1.03556288, 0.9881471])),
    ('fs-4', pd.Series([1.05234725, 1.037771, 1.0275516, 0.98820533])),
    ('multisi', pd.Series([1.03310403, 1.02391703, 1.01744833, 0.97947605])),
    ('monosi', pd.Series([1.03225083, 1.02335353, 1.01708734, 0.97950110])),
    ('cigs', pd.Series([1.01475834, 1.01143927, 1.00909094, 0.97852966])),
])
def test_spectral_factor_pvspec_series(module_type, expected):
    ams = pd.Series([1.0, 1.5, 2.0, 1.5])
    kcs = pd.Series([0.4, 0.6, 0.8, 1.4])
    out = spectrum.spectral_factor_pvspec(ams, kcs,
                                          module_type=module_type)
    assert isinstance(out, pd.Series)
    assert np.allclose(expected, out, atol=1e-8)


def test_spectral_factor_pvspec_supplied():
    # use the multisi coeffs
    coeffs = (0.9847, -0.05237, 0.03034)
    out = spectrum.spectral_factor_pvspec(1.5, 0.8, coefficients=coeffs)
    expected = 1.00860641
    assert_allclose(out, expected, atol=1e-8)


def test_spectral_factor_pvspec_supplied_redundant():
    # Error when specifying both module_type and coefficients
    coeffs = (0.9847, -0.05237, 0.03034)
    with pytest.raises(ValueError, match='supply only one of'):
        spectrum.spectral_factor_pvspec(1.5, 0.8, module_type='multisi',
                                        coefficients=coeffs)


def test_spectral_factor_pvspec_supplied_ambiguous():
    # Error when specifying neither module_type nor coefficients
    with pytest.raises(ValueError, match='No valid input provided'):
        spectrum.spectral_factor_pvspec(1.5, 0.8, module_type=None,
                                        coefficients=None)


@pytest.mark.parametrize("module_type,expected", [
    ('multisi', np.array([1.06129, 1.03098, 1.01155, 0.99849])),
    ('cdte', np.array([1.09657,  1.05594, 1.02763, 0.97740])),
])
def test_spectral_factor_jrc(module_type, expected):
    ams = np.array([1.0, 1.5, 2.0, 1.5])
    kcs = np.array([0.4, 0.6, 0.8, 1.4])
    out = spectrum.spectral_factor_jrc(ams, kcs,
                                       module_type=module_type)
    assert np.allclose(expected, out, atol=1e-4)


@pytest.mark.parametrize("module_type,expected", [
    ('multisi', np.array([1.06129, 1.03098, 1.01155, 0.99849])),
    ('cdte', np.array([1.09657,  1.05594, 1.02763, 0.97740])),
])
def test_spectral_factor_jrc_series(module_type, expected):
    ams = pd.Series([1.0, 1.5, 2.0, 1.5])
    kcs = pd.Series([0.4, 0.6, 0.8, 1.4])
    out = spectrum.spectral_factor_jrc(ams, kcs,
                                       module_type=module_type)
    assert isinstance(out, pd.Series)
    assert np.allclose(expected, out, atol=1e-4)


def test_spectral_factor_jrc_supplied():
    # use the multisi coeffs
    coeffs = (0.494, 0.146, 0.00103)
    out = spectrum.spectral_factor_jrc(1.0, 0.8, coefficients=coeffs)
    expected = 1.01052106
    assert_allclose(out, expected, atol=1e-4)


def test_spectral_factor_jrc_supplied_redundant():
    # Error when specifying both module_type and coefficients
    coeffs = (0.494, 0.146, 0.00103)
    with pytest.raises(ValueError, match='supply only one of'):
        spectrum.spectral_factor_jrc(1.0, 0.8, module_type='multisi',
                                     coefficients=coeffs)


def test_spectral_factor_jrc_supplied_ambiguous():
    # Error when specifying neither module_type nor coefficients
    with pytest.raises(ValueError, match='No valid input provided'):
        spectrum.spectral_factor_jrc(1.0, 0.8, module_type=None,
                                     coefficients=None)


@pytest.fixture
def sr_and_eqe_fixture():
    # Just some arbitrary data for testing the conversion functions
    df = pd.DataFrame(
        columns=("wavelength", "quantum_efficiency", "spectral_response"),
        data=[
            # nm, [0,1], A/W
            [300, 0.85, 0.205671370402405],
            [350, 0.86, 0.242772872514211],
            [400, 0.87, 0.280680929019753],
            [450, 0.88, 0.319395539919029],
            [500, 0.89, 0.358916705212040],
            [550, 0.90, 0.399244424898786],
            [600, 0.91, 0.440378698979267],
            [650, 0.92, 0.482319527453483],
            [700, 0.93, 0.525066910321434],
            [750, 0.94, 0.568620847583119],
            [800, 0.95, 0.612981339238540],
            [850, 0.90, 0.617014111207215],
            [900, 0.80, 0.580719163489143],
            [950, 0.70, 0.536358671833723],
            [1000, 0.6, 0.483932636240953],
            [1050, 0.4, 0.338752845368667],
        ],
    )
    df.set_index("wavelength", inplace=True)
    return df


def test_sr_to_qe(sr_and_eqe_fixture):
    # vector type
    qe = spectrum.sr_to_qe(
        sr_and_eqe_fixture["spectral_response"].values,
        sr_and_eqe_fixture.index.values,  # wavelength, nm
    )
    assert_allclose(qe, sr_and_eqe_fixture["quantum_efficiency"])
    # pandas series type
    # note: output Series' name should match the input
    qe = spectrum.sr_to_qe(
        sr_and_eqe_fixture["spectral_response"]
    )
    pd.testing.assert_series_equal(
        qe, sr_and_eqe_fixture["quantum_efficiency"],
        check_names=False
    )
    assert qe.name == "spectral_response"
    # series normalization
    qe = spectrum.sr_to_qe(
        sr_and_eqe_fixture["spectral_response"] * 10, normalize=True
    )
    pd.testing.assert_series_equal(
        qe,
        sr_and_eqe_fixture["quantum_efficiency"]
        / max(sr_and_eqe_fixture["quantum_efficiency"]),
        check_names=False,
    )
    # error on lack of wavelength parameter if no pandas object is provided
    with pytest.raises(TypeError, match="must have an '.index' attribute"):
        _ = spectrum.sr_to_qe(sr_and_eqe_fixture["spectral_response"].values)


def test_qe_to_sr(sr_and_eqe_fixture):
    # vector type
    sr = spectrum.qe_to_sr(
        sr_and_eqe_fixture["quantum_efficiency"].values,
        sr_and_eqe_fixture.index.values,  # wavelength, nm
    )
    assert_allclose(sr, sr_and_eqe_fixture["spectral_response"])
    # pandas series type
    # note: output Series' name should match the input
    sr = spectrum.qe_to_sr(
        sr_and_eqe_fixture["quantum_efficiency"]
    )
    pd.testing.assert_series_equal(
        sr, sr_and_eqe_fixture["spectral_response"],
        check_names=False
    )
    assert sr.name == "quantum_efficiency"
    # series normalization
    sr = spectrum.qe_to_sr(
        sr_and_eqe_fixture["quantum_efficiency"] * 10, normalize=True
    )
    pd.testing.assert_series_equal(
        sr,
        sr_and_eqe_fixture["spectral_response"]
        / max(sr_and_eqe_fixture["spectral_response"]),
        check_names=False,
    )
    # error on lack of wavelength parameter if no pandas object is provided
    with pytest.raises(TypeError, match="must have an '.index' attribute"):
        _ = spectrum.qe_to_sr(
            sr_and_eqe_fixture["quantum_efficiency"].values
        )


def test_qe_and_sr_reciprocal_conversion(sr_and_eqe_fixture):
    # test that the conversion functions are reciprocal
    qe = spectrum.sr_to_qe(sr_and_eqe_fixture["spectral_response"])
    sr = spectrum.qe_to_sr(qe)
    assert_allclose(sr, sr_and_eqe_fixture["spectral_response"])
    qe = spectrum.sr_to_qe(sr)
    assert_allclose(qe, sr_and_eqe_fixture["quantum_efficiency"])
