# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2010-2011, GEM Foundation.
#
# OpenQuake is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# only, as published by the Free Software Foundation.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License version 3 for more details
# (a copy is included in the LICENSE file that accompanied this code).
#
# You should have received a copy of the GNU Lesser General Public License
# version 3 along with OpenQuake.  If not, see
# <http://www.gnu.org/licenses/lgpl-3.0.txt> for a copy of the LGPLv3 License.



"""
Tests of the supported GEM output formats.
Goals of this test suite should be to test valid and invalid input,
validate all capabilities of the formats (e.g., coordinate and projection),
and (eventually) test performance of various serializers.
"""

import os
import numpy
import struct
import subprocess
import unittest

from osgeo import gdal, gdalconst

from openquake import shapes
from utils import test
from openquake.output import geotiff
from openquake.output import curve

# we define some test regions which have a lower-left corner at 0.0/0.0
# the default grid spacing of 0.1 degrees is used
# order of region envelope vertices is:
# (lower-left, lower-right, upper-right, upper-left)
# this is made from a shapely polygon, which has (lon, lat) vertices
# N-S direction is rows, W-E direction is columns of the underlying
# numpy array

# 11x6 px (numpy array: 6x11) test region
TEST_REGION_SMALL = [(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)]

# 11x11 px test region
TEST_REGION_SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

# 101x51 px (numpy array: 51x101) test region
TEST_REGION_LARGE_ASYMMETRIC = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0),
                                (0.0, 5.0)]

GEOTIFF_FILENAME_WITHOUT_NUMBER = "test.smallregion.tiff"
GEOTIFF_FILENAME_WITH_NUMBER = "test.smallregion.1.tiff"
GEOTIFF_FILENAME_SQUARE_REGION = "test.squareregion.tiff"
GEOTIFF_FILENAME_LARGE_ASYMMETRIC_REGION = "test.asymmetric.region.tiff"
GEOTIFF_FILENAME_COLORSCALE = "test.colorscale.tiff"
GEOTIFF_FILENAME_COLORSCALE_CUTS = "test.colorscale-cuts.tiff"
GEOTIFF_LOSS_RATIO_MAP_COLORSCALE = "test.loss_ratio_map.tiff"
GEOTIFF_FILENAME_EXPLICIT_COLORSCALE_BINS = "test.colorscale-bins.tiff"
GEOTIFF_FILENAME_NONDEFAULT_COLORSCALE = "test.colorscale-nondefault.tiff"
GEOTIFF_FILENAME_MULTISEGMENT_COLORSCALE = "test.colorscale-multisegment.tiff"
GEOTIFF_FILENAME_DISCRETE_COLORSCALE = "test.colorscale-discrete.tiff"
GEOTIFF_FILENAME_DISCRETE_CUSTOMBIN_COLORSCALE = \
    "test.colorscale-discrete-custombins.tiff"

HAZARDCURVE_PLOT_SIMPLE_FILENAME = "hazard-curves-simple.svg"

HAZARDCURVE_PLOT_FILENAME = "hazard-curves.svg"
HAZARDCURVE_PLOT_INPUTFILE = "example-hazard-curves-for-plotting.xml"

LOSS_CURVE_PLOT_FILENAME = "loss-curves.svg"
LOSS_CURVE_PLOT_INPUTFILE = "example-loss-curves-for-plotting.xml"

LOSS_RATIO_CURVE_PLOT_FILENAME = "loss-ratio-curves.svg"
LOSS_RATIO_CURVE_PLOT_INPUTFILE = "example-loss-ratio-curves-for-plotting.xml"

GEOTIFF_USED_CHANNEL_IDX = 1
GEOTIFF_TOTAL_CHANNELS = 4
GEOTIFF_TEST_PIXEL_VALUE = 1.0

TEST_COLORMAP = {
    'id': 'seminf-haxby.cpt,v 1.1 2004/02/25 18:15:50 jjg Exp',
    'name': 'seminf-haxby',
    'type': 'discrete',
    'model': 'RGB',
    # z_values = [0.0, 1.25, ... , 28.75, 30.0]
    'z_values': [1.25 * x for x in range(25)],
    'red': [255, 208, 186, 143, 97, 0, 25, 12, 24, 49, 67, 96,
            105, 123, 138, 172, 205, 223, 240, 247, 255,
            255, 244, 238],
    'green': [255, 216, 197, 161, 122, 39, 101, 129, 175, 190,
              202, 225, 235, 235, 236, 245, 255, 245, 236,
              215, 189, 160, 116, 79],
    'blue': [255, 251, 247, 241, 236, 224, 240, 248, 255, 255,
             255, 240, 225, 200, 174, 168, 162, 141, 120,
             103, 86, 68, 74, 77],
    'background': [255, 255, 255],
    'foreground': [238, 79, 77],
    'NaN': [0, 0, 0]}


class OutputTestCase(unittest.TestCase):
    """Test all our output file formats, generally against sample content"""

    def test_geotiff_generation_discrete_colorscale_custom_bins(self):
        """Check RGB geotiff generation with colorscale for GMF. Use
        discrete colorscale based on IML values, with custom IML."""
        path = test.do_test_output_file(
            GEOTIFF_FILENAME_DISCRETE_CUSTOMBIN_COLORSCALE)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)

        iml_list = [0.005, 0.007, 0.0098, 0.0137, 0.0192, 0.0269, 0.0376,
                    0.0527, 0.0738, 0.103, 0.145, 0.203, 0.284, 0.397,
                    0.556, 0.778, 1.09, 1.52, 2.13]

        gwriter = geotiff.GMFGeoTiffFile(path, asymmetric_region.grid,
            iml_list=iml_list, discrete=True, colormap='matlab-polar')

        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            self._colorscale_cuts_fill)
        gwriter.close()

    def test_geotiff_generation_discrete_colorscale(self):
        """Check RGB geotiff generation with colorscale for GMF. Use
        discrete colorscale based on IML values, with default IML."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_DISCRETE_COLORSCALE)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)

        gwriter = geotiff.GMFGeoTiffFile(path, asymmetric_region.grid,
            iml_list=None, discrete=True, colormap='gmt-seis')

        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            self._colorscale_cuts_fill)
        gwriter.close()

    def test_geotiff_generation_multisegment_colorscale(self):
        """Check RGB geotiff generation with colorscale for GMF. Use
        multisegment colorscale."""
        path = test.do_test_output_file(
            GEOTIFF_FILENAME_MULTISEGMENT_COLORSCALE)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)

        gwriter = geotiff.GMFGeoTiffFile(path, asymmetric_region.grid,
            iml_list=None, discrete=False, colormap='gmt-seis')

        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            self._colorscale_cuts_fill)
        gwriter.close()

    def test_geotiff_generation_nondefault_colorscale(self):
        """Check RGB geotiff generation with colorscale for GMF. Use
        alternative colorscale."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_NONDEFAULT_COLORSCALE)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)

        gwriter = geotiff.GMFGeoTiffFile(path, asymmetric_region.grid,
            iml_list=None, discrete=False, colormap='gmt-green-red')

        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            self._colorscale_cuts_fill)
        gwriter.close()

    def test_geotiff_generation_explicit_colorscale_bins(self):
        """Check RGB geotiff generation with colorscale for GMF. Limits
        and bins of colorscale are explicitly given."""
        path = test.do_test_output_file(
            GEOTIFF_FILENAME_EXPLICIT_COLORSCALE_BINS)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)

        for test_number, test_list in enumerate(([0.9, 0.95, 1.0, 1.05],
                                                 None)):

            curr_path = "%s.%s.tiff" % (path[0:-5], test_number)
            gwriter = geotiff.GMFGeoTiffFile(curr_path,
                asymmetric_region.grid, iml_list=test_list, discrete=False)

            reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                            asymmetric_region.grid.columns),
                                           dtype=numpy.float)
            self._fill_rasters(asymmetric_region, gwriter, reference_raster,
                self._colorscale_cuts_fill)
            gwriter.close()

    def test_geotiff_generation_colorscale_cuts(self):
        """Check RGB geotiff generation with colorscale for GMF."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_COLORSCALE_CUTS)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)
        gwriter = geotiff.GMFGeoTiffFile(path, asymmetric_region.grid,
            discrete=False)

        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            self._colorscale_cuts_fill)
        gwriter.close()

    def test_geotiff_generation_colorscale(self):
        """Check RGB geotiff generation with colorscale for GMF."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_COLORSCALE)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)
        gwriter = geotiff.GMFGeoTiffFile(path, asymmetric_region.grid,
            discrete=False)

        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            self._colorscale_fill)
        gwriter.close()

    def test_geotiff_loss_ratio_map_colorscale(self):
        path = test.do_test_output_file(GEOTIFF_LOSS_RATIO_MAP_COLORSCALE)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)

        gwriter = geotiff.LossMapGeoTiffFile(path, asymmetric_region.grid,
            normalize=True)
        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)

        color_fill = lambda x, y:  (x * y) / 50
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            color_fill)
        gwriter.close()

        self._assert_geotiff_metadata_is_correct(path, asymmetric_region)
        self._assert_geotiff_band_min_max_values(path,
            GEOTIFF_USED_CHANNEL_IDX, 0, 240)

    def test_loss_ratio_curve_plot_generation_multiple_sites(self):
        """Create SVG plots for loss ratio curves read from an NRML file. The
        file contains data for several sites.
        For each site, a separate SVG file is created."""

        path = test.do_test_output_file(LOSS_RATIO_CURVE_PLOT_FILENAME)
        loss_ratio_curve_path = test.do_test_file(
            LOSS_RATIO_CURVE_PLOT_INPUTFILE)

        plotter = curve.RiskCurvePlotter(path, loss_ratio_curve_path,
            mode='loss_ratio')

        # delete expected output files, if existing
        for svg_file in plotter.filenames():
            if os.path.isfile(svg_file):
                os.remove(svg_file)

        plotter.plot(autoscale_y=False)

        # assert that for each site in the NRML file an SVG has been created
        for svg_file in plotter.filenames():
            self.assertTrue(os.path.getsize(svg_file) > 0)

    def test_loss_curve_plot_generation_multiple_sites(self):
        """Create SVG plots for loss curves read from an NRML file. The
        file contains data for several sites.
        For each site, a separate SVG file is created."""

        path = test.do_test_output_file(LOSS_CURVE_PLOT_FILENAME)
        loss_curve_path = test.do_test_file(LOSS_CURVE_PLOT_INPUTFILE)

        plotter = curve.RiskCurvePlotter(path, loss_curve_path, mode='loss',
            curve_title="This is a test loss curve")

        # delete expected output files, if existing
        for svg_file in plotter.filenames():
            if os.path.isfile(svg_file):
                os.remove(svg_file)

        plotter.plot(autoscale_y=True)

        # assert that for each site in the NRML file an SVG has been created
        for svg_file in plotter.filenames():
            self.assertTrue(os.path.getsize(svg_file) > 0)

    def test_loss_curve_plot_generation_multiple_sites_render_multi(self):
        """Create SVG plots for loss curves read from an NRML file. The
        file contains data for several sites.
        For each site, a separate SVG file is created."""

        path = test.do_test_output_file(LOSS_CURVE_PLOT_FILENAME)
        loss_curve_path = test.do_test_file(LOSS_CURVE_PLOT_INPUTFILE)

        plotter = curve.RiskCurvePlotter(path, loss_curve_path, mode='loss',
            curve_title="This is a test loss curve", render_multi=True)

        # delete expected output files, if existing
        for svg_file in plotter.filenames():
            if os.path.isfile(svg_file):
                os.remove(svg_file)

        plotter.plot(autoscale_y=True)

        for svg_file in plotter.filenames():
            self.assertTrue(os.path.getsize(svg_file) > 0)

    def test_simple_curve_plot_generation(self):
        """Create an SVG plot of a single (hazard) curve for a single site
        from a dictionary."""

        test_site = shapes.Site(-122, 38)
        test_end_branch = '1_1'
        test_hc_data = {test_end_branch:
                {'abscissa': [0.0, 1.0, 1.8],
                 'ordinate': [1.0, 0.5, 0.2],
                 'abscissa_property': 'PGA',
                 'ordinate_property': 'Probability of Exceedance',
                 'curve_title': 'Hazard Curve',
                 'Site': test_site}}

        path = test.do_test_output_file(HAZARDCURVE_PLOT_SIMPLE_FILENAME)
        plot = curve.CurvePlot(path)
        plot.write(test_hc_data)
        plot.close()

        # assert that file has been created and is not empty
        self.assertTrue(os.path.getsize(path) > 0)
        os.remove(path)

    def test_hazardcurve_plot_generation_multiple_sites_multiple_curves(self):
        """Create SVG plots for hazard curves read from an NRML file. The
        file contains data for several sites, and several end branches of
        the logic tree. For each site, a separate SVG file is created."""

        path = test.do_test_output_file(HAZARDCURVE_PLOT_FILENAME)
        hazardcurve_path = test.do_test_file(HAZARDCURVE_PLOT_INPUTFILE)

        plotter = curve.HazardCurvePlotter(path, hazardcurve_path,
            curve_title='Example Hazard Curves')

        # delete expected output files, if existing
        for svg_file in plotter.filenames():
            if os.path.isfile(svg_file):
                os.remove(svg_file)

        plotter.plot()

        # assert that for each site in the NRML file an SVG has been created
        # and is not empty
        for svg_file in plotter.filenames():
            self.assertTrue(os.path.getsize(svg_file) > 0)
            os.remove(svg_file)

    def test_geotiff_generation_and_metadata_validation(self):
        """Create a GeoTIFF, and check if it has the
        correct metadata."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_WITHOUT_NUMBER)
        smallregion = shapes.Region.from_coordinates(TEST_REGION_SMALL)
        gwriter = geotiff.GeoTiffFile(path, smallregion.grid)
        gwriter.close()

        self._assert_geotiff_metadata_is_correct(path, smallregion)

    def test_geotiff_generation_with_number_in_filename(self):
        """Create a GeoTIFF with a number in its filename. This
        test has been written because it has been reported that numbers in the
        filename do not work."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_WITH_NUMBER)
        smallregion = shapes.Region.from_coordinates(TEST_REGION_SMALL)
        gwriter = geotiff.GeoTiffFile(path, smallregion.grid)
        gwriter.close()

        self._assert_geotiff_metadata_is_correct(path, smallregion)

    def test_geotiff_generation_initialize_raster(self):
        """Create a GeoTIFF and initialize the raster to a given value. Then
        check through metadata if it has been done correctly. We check the
        minumum and maximum values of the band, which are expected to have
        the value of the raster nodes."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_WITH_NUMBER)
        smallregion = shapes.Region.from_coordinates(TEST_REGION_SMALL)
        gwriter = geotiff.GeoTiffFile(path, smallregion.grid,
                                      GEOTIFF_TEST_PIXEL_VALUE)
        gwriter.close()

        self._assert_geotiff_metadata_is_correct(path, smallregion)

        # assert that all raster pixels have the desired value
        self._assert_geotiff_band_min_max_values(path,
            GEOTIFF_USED_CHANNEL_IDX,
            GEOTIFF_TEST_PIXEL_VALUE,
            GEOTIFF_TEST_PIXEL_VALUE)

    def test_geotiff_generation_and_simple_raster_validation(self):
        """Create a GeoTIFF and assign values to the raster nodes according
        to a simple function. Then check if the raster values have been set
        correctly."""
        path = test.do_test_output_file(GEOTIFF_FILENAME_SQUARE_REGION)
        squareregion = shapes.Region.from_coordinates(TEST_REGION_SQUARE)
        gwriter = geotiff.GeoTiffFile(path, squareregion.grid)

        reference_raster = numpy.zeros((squareregion.grid.rows,
                                        squareregion.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(squareregion, gwriter, reference_raster,
            self._trivial_fill)
        gwriter.close()

        self._assert_geotiff_metadata_and_raster_is_correct(path,
            squareregion, GEOTIFF_USED_CHANNEL_IDX, reference_raster)

    def test_geotiff_generation_asymmetric_pattern(self):
        """Create a GeoTIFF and assign values to the raster nodes according
        to a simple function. Use a somewhat larger, non-square region for
        that. Then check if the raster values have been set correctly."""
        path = test.do_test_output_file(
            GEOTIFF_FILENAME_LARGE_ASYMMETRIC_REGION)
        asymmetric_region = shapes.Region.from_coordinates(
            TEST_REGION_LARGE_ASYMMETRIC)
        gwriter = geotiff.GeoTiffFile(path, asymmetric_region.grid)

        reference_raster = numpy.zeros((asymmetric_region.grid.rows,
                                        asymmetric_region.grid.columns),
                                       dtype=numpy.float)
        self._fill_rasters(asymmetric_region, gwriter, reference_raster,
            self._trivial_fill)
        gwriter.close()

        self._assert_geotiff_metadata_and_raster_is_correct(path,
            asymmetric_region, GEOTIFF_USED_CHANNEL_IDX, reference_raster)

    @test.skipit
    def test_geotiff_output(self):
        """Generate a geotiff file with a smiley face."""
        path = test.do_test_file("test.1.tiff")
        switzerland = shapes.Region.from_coordinates(
            [(10.0, 100.0), (100.0, 100.0), (100.0, 10.0), (10.0, 10.0)])
        image_grid = switzerland.grid
        gwriter = geotiff.GeoTiffFile(path, image_grid)
        for xpoint in range(0, 320):
            for ypoint in range(0, 320):
                gwriter.write((xpoint, ypoint), int(xpoint * 254 / 320))
        gwriter.close()

        comp_path = os.path.join(test.DATA_DIR, "test.tiff")
        retval = subprocess.call(["tiffcmp", "-t", path, comp_path],
            stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        self.assertTrue(retval == 0)
        # TODO(jmc): Figure out how to validate the geo coordinates as well
        # TODO(jmc): Use validation that supports tiled geotiffs

    def _assert_geotiff_metadata_is_correct(self, path, region):

        # open GeoTIFF file and assert that metadata is correct
        dataset = gdal.Open(path, gdalconst.GA_ReadOnly)
        self.assertEqual(dataset.RasterXSize, region.grid.columns)
        self.assertEqual(dataset.RasterYSize, region.grid.rows)
        self.assertEqual(dataset.RasterCount, GEOTIFF_TOTAL_CHANNELS)

        (origin_lon, lon_pixel_size, lon_rotation, origin_lat, lat_rotation,
            lat_pixel_size) = dataset.GetGeoTransform()

        self.assertAlmostEqual(origin_lon,
            region.grid.region.upper_left_corner.longitude)
        self.assertAlmostEqual(origin_lat,
            region.grid.region.upper_left_corner.latitude)
        self.assertAlmostEqual(lon_pixel_size, region.grid.cell_size)
        self.assertAlmostEqual(lat_pixel_size, -region.grid.cell_size)

    def _assert_geotiff_band_min_max_values(self, path, band_index,
        min_value, max_value):

        # open GeoTIFF file and assert that min and max values
        # of a band are correct
        dataset = gdal.Open(path, gdalconst.GA_ReadOnly)
        band = dataset.GetRasterBand(band_index)
        (band_min, band_max) = band.ComputeRasterMinMax(band_index)

        self.assertAlmostEqual(band_min, min_value)
        self.assertAlmostEqual(band_max, max_value)

    def _assert_geotiff_raster_is_correct(self, path, band_index, raster):

        # open GeoTIFF file and assert that the image raster is correct
        dataset = gdal.Open(path, gdalconst.GA_ReadOnly)
        band = dataset.GetRasterBand(band_index)

        band_raster = numpy.zeros((band.YSize, band.XSize), dtype=numpy.float)
        for row_idx in xrange(band.YSize):

            scanline = band.ReadRaster(0, row_idx, band.XSize, 1,
                band.XSize, 1, geotiff.GDAL_PIXEL_DATA_TYPE)

            tuple_of_floats = struct.unpack('f' * band.XSize, scanline)
            band_raster[row_idx, :] = tuple_of_floats

        self.assertTrue(numpy.allclose(band_raster, raster))

    def _assert_geotiff_metadata_and_raster_is_correct(self, path, region,
                                                       band_index, raster):
        self._assert_geotiff_metadata_is_correct(path, region)
        self._assert_geotiff_raster_is_correct(path, GEOTIFF_USED_CHANNEL_IDX,
            raster)

    def _fill_rasters(self, region, writer, reference_raster, fill_function):
        for row_idx in xrange(region.grid.rows):
            for col_idx in xrange(region.grid.columns):
                writer.write((row_idx, col_idx), fill_function(row_idx,
                                                               col_idx))
                reference_raster[row_idx, col_idx] = fill_function(row_idx,
                                                                   col_idx)

    def _trivial_fill(self, row_idx, col_idx):
        return float((row_idx + 1) * (col_idx + 1))

    def _colorscale_fill(self, row_idx, col_idx):
        """if used with asymmetic large region, return value range 0..2"""
        return row_idx * col_idx / (5.0 * 10.0 * 100.0)

    def _colorscale_cuts_fill(self, row_idx, col_idx):
        """if used with asymmetic large region, return value
        range -1..4"""
        return (row_idx * col_idx / (10.0 * 100.0)) - 1.0

    def test_color_map_from_cpt_good_discrete(self):
        """
        Tests the CPTReader class by reading a known-good cpt file
        containing a discrete color scale.
        """
        test_file = 'seminf-haxby.cpt'
        test_path = os.path.join(test.DATA_DIR, test_file)

        reader = geotiff.CPTReader(test_path)
        expected_map = TEST_COLORMAP

        actual_map = reader.get_colormap()
        self.assertEqual(expected_map, actual_map)

    def test_hazard_map_geotiff_constructor_raises(self):
        """
        Test the parameter validation of the HazardMapGeoTiffFile constructor.
        """

        test_file_path = 'test.tiff'  # this test won't actually write anything
        test_region = shapes.Region.from_coordinates(TEST_REGION_SMALL)

        bad_test_data = (
            ('foo', 'bar'),
            ('foo', 17),
            (17, 'foo'),
            (-1.0, 5.5),
            (-2, -0.5),
            (2.13, 0.005))
        for bad in bad_test_data:
            self.assertRaises(
                (AssertionError, ValueError), geotiff.HazardMapGeoTiffFile, test_file_path,
                test_region.grid, TEST_COLORMAP, iml_min_max=bad)

    def test_hazard_map_geotiff_scaling_fixed(self):
        """
        Scaling type for a HazardMapGeoTiffFile is 'fixed' if the iml_min_max
        is specified in the constructor.

        This test ensures the scaling type is properly set to 'fixed'.
        """
        # Nothing is actually written to this file in this test
        test_file_path = "test.tiff"
        test_region = shapes.Region.from_coordinates(TEST_REGION_SMALL)
        test_iml_min_max = ('0.0', '4.8')

        # test 'fixed' color scaling
        hm_writer = geotiff.HazardMapGeoTiffFile(
            test_file_path, test_region.grid, TEST_COLORMAP,
            iml_min_max=test_iml_min_max)
        self.assertEqual('fixed', hm_writer.scaling)

    def test_hazard_map_geotiff_scaling_relative(self):
        """
        Scaling type for a HazardMapGeoTiffFile is 'relative' if the
        iml_min_max is not specified in the constructor. Instead, the min and
        max values are derived from the lowest and highest existing values in
        the hazard map raster (the min and max values are calculated later when
        the raw raster values are normalized; see the HazardMapGeoTiffFile
        class doc for more info).

        This test ensures that the scaling type is properly set to 'relative'.
        """
        # Nothing is actually written to this file in this test
        test_file_path = "test.tiff"
        test_region = shapes.Region.from_coordinates(TEST_REGION_SMALL)

        # test 'relative' color scaling
        hm_writer = geotiff.HazardMapGeoTiffFile(
            test_file_path, test_region.grid, TEST_COLORMAP)
        self.assertEqual('relative', hm_writer.scaling)
