# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pipeline Classes and functions
==============================

This files contains the pipeline for the MRBLEs analysis.

.. figure::  ../images/pipeline-diagram.png
   :align:   center

"""

# [Future imports]
from __future__ import (absolute_import, division, print_function)
from builtins import (str, super, range, int, object)

# [File header]     | Copy and edit for each file in this project!
# title             : simp.py
# description       : MRBLEs - Simplified and condensed functions.
# author            : Bjorn Harink
# credits           :
# date              : 20170219

# [Modules]
# General Python
import os
import re
# import warnings
# import sys
import gc
from math import sqrt
from random import randint

# Other
import numpy as np
import scipy as sp
from scipy import ndimage as ndi
from sklearn.metrics import silhouette_score
import pandas as pd
import weightedstats as ws
import xarray as xr
from matplotlib import pyplot as plt
from skimage.external import tifffile as tff

# # Plotting
# import plotly.graph_objs as go
# from plotly.offline import init_notebook_mode, iplot # For plotly offline mode

# Intra-Package dependencies
from mrbles.core import FindBeadsImaging, ICP, Classify, SpectralUnmixing
from mrbles.data import ImageSetRead, ImageDataFrame, TableDataFrame
from mrbles.report import ClusterCheck


# General methods


class Settings(object):
    """Settings object."""

    def __init__(self, objects, object_names):
        """Set attributes for given objects."""
        for idx, obj in enumerate(objects):
            setattr(self, object_names[idx], obj)


# Classes


class Images(ImageDataFrame):
    """Load images into mrbles dataframe.

    There are two methods to load images into the mrbles dataframe:
    Method 1 - Provide dictionaries with folder and filename patterns.
    Method 2 - Provide a dictionary with numpy arrays.

    This class facilitates loading images into the mrbles.data.ImageDataFrame.
    Please see this class documentation for more information.

    For loading OME-TIFF image it uses mrbles.data.ImageSetRead.
    Please see this class documentation for more information.

    Method 1 - Example
    ------------------
    >>> assay_folder = '../data'
    >>> assay_folders = {'Set 1': '../data1',
                         'Set 2': '../data2'}
    >>> assay_files = {'Set 1': 'image_set1_(0-9)(0-9).ome.tif',
                       'Set 2': 'image_set2_(0-9)(0-9).ome.tif'}
    >>> assay_images = mrbles.Images(assay_folder, assay_files)
        Found 12 files in Set 1
        Found 11 files in Set 2

    Method 2 - Example
    ------------------
    >>> image_arrays = {'Set 1': numpy_array_1,
                        'Set 2': numpy_array_2}
    >>> channel_names = ['Brightfield', 'Cy5', 'l-435', 'l-546', 'l-620']
    >>> assay_images = mrbles.Images(data=image_arrays, channels=channel_names)

    Output - Example
    ----------------
    >>> assay_images
        {'Set 1': <xarray.DataArray (f: 12, c: 5, y: 1024, x: 1024)>
            array([[[[169., ..., 166.],
                    ...,
                    [101., ..., 121.]]]])
            Coordinates:
            * c        (c) object 'Brightfield', 'Cy5', 'l-435', 'l-546', ...
            Dimensions without coordinates: f, y, x,
        'Set 2': ...
    >>> assay_images['Set 2', 3, 'Brightfield']
        <xarray.DataArray (y: 1024, x: 1024)>
        array([[188., 163., 182., ..., 188., 174., 170.],
                ...,
               [144., 141., 142., ..., 162., 162., 154.]])
        Coordinates:
            c        <U11 'Brightfield'
        Dimensions without coordinates: y, x

    Parameters
    ----------
    folders : str, dict
        String of single folder or dict of multiple folders.
        The folder(s) provided will searched recursively.
        Dict keys must match file_patterns dict.
    file_patterns : dict
        Dict of multiple file patterns.
        Dict keys must match folders keys, if multiple folders.
    data : NumPy array
        Alternative method to loading OME-Tif files.
        Load a dict of NumPy arrays with dimension order (f, c, y, x):
        files (f), channels (c), Y-dimension (y), X-dimension (x)
    channels : list of str
        List of channel names.
        Defaults to None. Channels will be numbers.

    Attributes
    ----------
    crop_x : slice
        Used for setting ROI slice in the X dimension.
    crop_y : slice
        Used for setting ROI slice in the Y dimension.

    """

    def __init__(self, folders=None, file_patterns=None,
                 data=None, channels=None):
        super(Images, self).__init__()
        self.folders = folders
        self.file_patterns = file_patterns
        self._dataframe = None
        self.files = None
        if (folders and file_patterns) is not None:
            self.files = self._find_images(self.folders, self.file_patterns)
            if isinstance(self.files, dict):
                for key, value in self.files.items():
                    if value is None:
                        print("No files found in %s with given parameters."
                              % (key))
                    else:
                        print("Found %i files in %s"
                              % (len(value), key))
        else:
            self._dataframe = {}
            if channels is None:
                coords = list(range(next(iter(data.values())).shape[1]))
            else:
                coords = channels
            if isinstance(data, dict):
                for data_key, data_array in data.items():
                    self._dataframe[data_key] = xr.DataArray(
                        data_array,
                        dims=['f', 'c', 'y', 'x'],
                        coords={'c': coords},
                        encoding={'dtype': np.uint16})

    def load(self, series=0):
        """Load images in memory."""
        if self.files is None:
            return False
        self._dataframe = {key: ImageSetRead(file_set, series).xdata
                           for key, file_set in self.files.items()}

    def add_images(self, images):
        """Add images to dataframe."""
        self.combine(images)
        gc.collect()

    def rename_channel(self, old_name, new_name):
        """Rename channel name.

        Parameters
        ----------
        old_name : str
            Original name of channel.
        new_name : str
            New name for old_name channel.

        """
        if isinstance(self._dataframe, dict):
            for key, data_array in self._dataframe.items():
                channels = data_array.coords['c'].values
                if old_name in channels:
                    self._dataframe[key] = self._rename_coord(data_array,
                                                              'c',
                                                              old_name,
                                                              new_name)
        else:
            self._dataframe = self._rename_coord(self._dataframe,
                                                 'c',
                                                 old_name,
                                                 new_name)

    def flat_field(self, ff_image, channel, affix='_FF'):
        """Flat-Field correction.

        Parameters
        ----------
        ff_image : str, NumPy array
            Flat-field image file or NumPy array.
        channel : str
            Channel to apply flat-field correction.
        affix : str
            Affix for channel name to be appended.
            Defaults to '_FF'

        """
        if isinstance(ff_image, str):
            flat_field = tff.TiffFile(ff_image).asarray()
        else:
            flat_field = ff_image
        flat_field = flat_field / flat_field.max()  # Normalize Flat-Field
        if isinstance(self._dataframe, dict):
            ff_dict_df = {}
            for key in self._dataframe.keys():
                ff_df = self._dataframe[key].loc[:, [channel]]
                ff_dict_df[key] = ff_df / flat_field
                ff_dict_df[key] = self._rename_coord(
                    ff_dict_df[key], 'c', channel, "%s%s" % (channel, affix))
        self.combine(ff_dict_df)

    @staticmethod
    def _rename_coord(dataframe, dim, old_name, new_name):
        """Rename dimension coordinate in an Xarray DataArray."""
        coordinates = dataframe.coords[dim].values
        np.place(coordinates, coordinates == old_name, new_name)
        renamed_dataframe = xr.DataArray(dataframe,
                                         dims=dataframe.dims,
                                         coords={'c': coordinates})
        return renamed_dataframe

    # Private methods
    @classmethod
    def _find_images(cls, folders, files):
        if isinstance(folders, dict):
            files = {key: cls.scan_path(folders[key], pattern)
                     for key, pattern in files.items()}
        elif isinstance(folders, str):
            files = {key: cls.scan_path(folders, pattern)
                     for key, pattern in files.items()}
        else:
            return None
        return files

    # Static methods
    @staticmethod
    def scan_path(path, pattern="*.tif"):
        """Scan folder recursively for files matching the pattern.

        Parameters
        ----------
        path : string
            Folder path as string, e.g. r'C:/folder/file.tif'.
        pattern : string
            File extenstion of general file pattern as search string,
            e.g. 'peptides_x_([0-9][0-9])_MMStack_Pos0.ome.tif'
            Defaults to '*.tif'.

        """
        image_files = []
        reg_object = re.compile(pattern)
        for root, _, files in os.walk(path):
            file_list = [os.path.join(root, x)
                         for x in files if reg_object.match(x)]
            if file_list:
                image_files.append(file_list)
        if not image_files:
            file_names = None
        else:
            file_names = np.hstack(image_files).tolist()
        return file_names


class Find(ImageDataFrame):
    """Find MRBLEs in brightfield images.

    This class provides the method to find MRBLEs and segment regions for each
    MRBLE in brightfield images, provided by mrbles.Images.

    Mask output: mask_full, mask_ring, mask_inside, mask_outside, mask_bkg, mask_check.

    Examples
    --------
    >>> find_mrbles = mrbles.Find(bead_size=18, pixel_size=3.5, border_clear=True, circle_size=350)
    >>> find_mrbles.settings.parallelize = True
    >>> find_mrbles.find(assay_images[:, : , 'Brightfield'])
        Bead diameter AVG: 54.36
        Bead diameter SD: 2.00
        Bead diameter CV: 3.68%
        Total number of beads: 2386
    >>> find_mrbles
        {'Set 1': <xarray.DataArray (f: 12, c: 6, y: 1024, x: 1024)>
            array([[[[0, ..., 0],
                      ...,
                     [0, ..., 0]]]], dtype=uint16)
            Coordinates:
            * c        (c) <U12 'mask_full' 'mask_ring' 'mask_inside' 'mask_outside' ...
            Dimensions without coordinates: f, y, x,
        'Set 2': ...
    >>> find_mrbles['Set 2', 3, 'mask_ring']
        <xarray.DataArray (y: 860, x: 860)>
        array([[0, 0, 0, ..., 0, 0, 0],
                ...,
               [0, 0, 0, ..., 0, 0, 0]], dtype=uint16)
        Coordinates:
            c        <U12 'mask_ring'
        Dimensions without coordinates: y, x

    Super-Class wrapper for mrbles.core.FindBeadsImaging.
    Please see this class documentation for more information.

    Parameters
    ----------
    bead_size : int
        Approximate width of beads (circles) in pixels.
    pixel_size : float
        Optional setting for image pixel size. Outputs dimensions using
        provided conversion value. Adds additional converted to database with
        affic '_conv'.
        Defaults to None.
    border_clear : boolean
        Beads touching border or ROI will be removed.
        Defaults to True.
    circle_size : int
        Set circle size for auto find circular ROI.

    Attributes
    ----------
    bead_dims : Pandas DataFrame
        Dataframe with individual MRBLE dimensions.
    beads_total : int
        Total number of MRBLEs found.
    beads_per_set : list of int
        Number of MRBLEs per set.
    settings : property
        Property provinding access to settings of mrbles.core.FindBeadsImaging.
        See property documentation for more information.

    """

    def __init__(self, bead_size, pixel_size=None,
                 border_clear=True, circle_size=None):
        super(Find, self).__init__()
        self._bead_size = bead_size
        self._pixel_size = pixel_size
        self._bead_objects = FindBeadsImaging(bead_size=bead_size,
                                              border_clear=border_clear,
                                              circle_size=circle_size)
        self._dataframe = None
        self._bead_dims = None

    def find(self, object_images, combine_data=None):
        """Execute finding images."""
        if isinstance(object_images, dict):
            self._dataframe, self._bead_dims = \
                self._find_multi_set(object_images)
        else:
            self._dataframe, self._bead_dims = \
                self._return_data(object_images)
        self._bead_dims.reset_index(inplace=True)
        self._bead_dims['diameter'] = self._bead_dims['radius'] * 2
        if self._pixel_size is not None:
            self._bead_dims['radius_conv'] = \
                self._bead_dims['radius'] * self._pixel_size
            self._bead_dims['perimeter_conv'] = \
                self._bead_dims['perimeter'] * self._pixel_size
            self._bead_dims['diameter_conv'] = \
                self._bead_dims['diameter'] * self._pixel_size
            self._bead_dims['area_conv'] = \
                self._bead_dims['area'] * self._pixel_size**2
            beads_diameter_mean = self.bead_dims.diameter_conv.mean()
            beads_diameter_sd = self.bead_dims.diameter_conv.std()
            converted = " (converted)"
        else:
            beads_diameter_mean = self.bead_dims.diameter.mean()
            beads_diameter_sd = self.bead_dims.diameter.std()
            converted = ""
        beads_diameter_cv = (beads_diameter_sd / beads_diameter_mean) * 100
        print("Bead diameter AVG%s: %0.2f" % (converted, beads_diameter_mean))
        print("Bead diameter SD%s: %0.2f" % (converted, beads_diameter_sd))
        print("Bead diameter CV%s: %0.2f%%" % (converted, beads_diameter_cv))
        if self.beads_per_set is not None:
            for key, value in self.beads_per_set.items():
                print("Number of beads in set %s: %i" % (key, value))
        print("Total number of beads: %i" % self.beads_total)
        if combine_data is not None:
            self.combine(combine_data)

    @property
    def bead_dims(self):
        """Return MRBLEs dimensions."""
        return self._bead_dims

    @property
    def beads_total(self):
        """Return total bead count in set(s)."""
        return self._bead_dims.shape[0]

    @property
    def beads_per_set(self):
        """Return total bead count in set(s)."""
        if self.sets is not None:
            bead_no_list = {set_x: self._bead_dims.loc[self._bead_dims['set'] == set_x].shape[0]
                            for set_x in self.sets}
        else:
            bead_no_list = None
        return bead_no_list

    @property
    def sets(self):
        """Return list of sets."""
        return TableDataFrame.get_set_names(self._bead_dims)

    def inspect(self, set_name=None, fig_num=3):
        """Display random images from set for inspection."""
        if not isinstance(self._dataframe, dict):
            img_num = self._dataframe.f.size
            self._inspect(self._dataframe, img_num, fig_num)
        elif set_name is None:
            img_num = {key: data.f.size
                       for key, data in self._dataframe.items()}
            for key, data in self._dataframe.items():
                self._inspect(data, img_num[key], fig_num)
                plt.suptitle(key)
        else:
            self._inspect(self._dataframe[set_name], img_num, fig_num)
            plt.suptitle(set_name)

    @staticmethod
    def _inspect(data, img_num, fig_num):
        plt.figure()
        for plt_num in range(1, fig_num + 1):
            rand_fig = randint(0, img_num)
            plt.subplot(1, fig_num, plt_num)
            plt.imshow(data.loc[rand_fig])
            plt.title('Figure #%s' % rand_fig)

    def _find_multi_set(self, object_image_sets):
        sets = list(object_image_sets.keys())
        data = [self._return_data(image_set)
                for key, image_set in object_image_sets.items()]
        data_masks = [i[0] for i in data]
        data_dims = [i[1] for i in data]
        result_masks = {
            sets[idx]: value for idx, value in enumerate(data_masks)
        }
        result_dims = pd.concat(data_dims,
                                keys=sets,
                                names=['set'])
        return result_masks, result_dims

    def _return_data(self, object_images):
        self._bead_objects.find(object_images)
        dataframe = self._bead_objects.data
        bead_dims = self._bead_objects.bead_dims
        return [dataframe, bead_dims]

    @property
    def settings(self):
        """Return FindBeadsImaging object for settings purposes.

        See FindBeadsImaging documentation for detailed settings.

        Examples
        --------
        >>> find_object = Find(bead_size=18)
        >>> find_object.settings.area_min = 20
        >>> find_object.settings.area_max = 350
        >>> find_object.settings.eccen_max = 0.65
        >>> find_object.settings.circle_size = 350

        """
        return self._bead_objects


class References(TableDataFrame):
    """Create reference spectra.

    There are three methods to load images into the this class:
    Method 1 - Provide a dictionaries with folders and filenames.
    Method 2 - Provide a dictionary with numpy arrays.
    Method 3 - Provide a file with spectra data.

    Parameters
    ----------
    folders : dict
        Dictionary with keywords (e.g. 'Dy', 'bkg') and folders.
        Must correspond with files parameter.
    files : dict
        Dictionary with keywords (e.g. 'Dy', 'bkg') and filenames.
        Must correspond with folders parameter.
    object_channel : str
        Channel to be used for finding MRBLEs
    reference_channels : list
        List of channel names to be used for generating reference spectra.
    bead_size : int
        Bead diamater set in pixels.
        Defaults to 16.
    dark_noise : int
        Dark noise of the camera used for the images.
        Defaults to 99 (median dark noise of Andor Zyla 4.2 PLUS sCMOS).

    Attributes
    ----------
    background : str
        Name of the background spectrum.
        Defaults to 'bkg'.
    crop_x : slice
        Crop X slice. Set with slice().
    crop_y : slice
        Crop Y slice. Set with slice().

    """

    def __init__(self, folders, files, object_channel, reference_channels,
                 bead_size=16, dark_noise=99):
        super(References, self).__init__()
        self._object_channel = object_channel
        self._ref_channels = reference_channels
        self._dark_noise = dark_noise
        self._images = Images(folders, files)
        self._find = Find(bead_size=bead_size,
                          border_clear=True,
                          circle_size=None)
        self._dataframe = None
        self._bkg_image = None
        # Attributes
        self.background = 'bkg'
        self.crop_x = slice(None)
        self.crop_y = slice(None)
        self.bkg_roi = [slice(None), slice(None)]
        # Settings options
        self.settings = Settings([self._images, self._find], ['icp', 'gmm'])
        self.settings.__doc__ = """Return Images and Find objects for settings purposes.

        Attributes
        ----------
        images : Images() object
            Returns Images() object for settings puproses.
            See class documentation for more information.
        find : Find() object
            Returns Find() object for settings puproses.
            See class documentation for more information.

        """

    def load(self):
        """Process all images and generate reference spectra."""
        self._images.load()
        spectra = list(self._images.data.keys())
        if len(self.bkg_roi) == 3:
            bkg_images = self._images[self.background, self.bkg_roi[2],
                                      self.bkg_roi[0], self.bkg_roi[1]]
        else:
            bkg_images = self._images[self.background, self._ref_channels,
                                      self.bkg_roi[0], self.bkg_roi[1]]
        self._bkg_image = self._images[self.background, self._object_channel,
                                       self.bkg_roi[0], self.bkg_roi[1]]
        spec_images = ImageDataFrame(self._images.data)
        spec_images._dataframe.pop(self.background, None)
        spec_images.crop_x = self.crop_x
        spec_images.crop_y = self.crop_y
        self._find.find(spec_images[:, self._object_channel])
        ref_channels = self._images[
            spectra[0], self._ref_channels].c.values
        data = [self.get_spectrum(self._dark_noise,
                                  spec_images[x_set, self._ref_channels],
                                  self._find[x_set, 'mask_inside'])
                for x_set in spectra if x_set != self.background]
        if self.background in spectra:
            spectra.remove(self.background)
            spectra.append(self.background)
            data.append(self._get_back(bkg_images))
        self._dataframe = pd.DataFrame(data=np.array(data).T,
                                       columns=spectra,
                                       index=ref_channels)
        self._dataframe.index.name = 'channels'
        self._clean_up()

    def _clean_up(self):
        del self._images
        del self._find
        gc.collect()

    def _get_back(self, bkg_images):
        mask = np.ones((bkg_images.y.size,
                        bkg_images.x.size))
        bkg_data = self.get_spectrum(0, bkg_images, mask)
        return bkg_data

    def plot(self, dpi=75):
        """Plot Reference spectra."""
        self._dataframe.plot()
        plt.figure(dpi=dpi)
        plt.title('Background slice')
        if self.background in self._dataframe:
            plt.imshow(self._bkg_image)

    @staticmethod
    def get_spectrum(dark_noise, channels, mask):
        """Get spectrum from image set using mask.

        The median of the masked area is extracted, the camera dark noise
        subtracted, and normalized.

        Parameters
        ----------
        dark_noise : int
            Intrinsic dark noise of camera. Image taken when shutter closed.
        channels : slice, list
            Slice of channels
        mask : NumPy array
            Labeled mask.

        """
        data = np.array([ndi.median(ch, mask) for ch in channels])
        data -= dark_noise  # Dark noise subtract
        data /= data.sum()  # Normalize to 1.
        return data


class Ratio(ImageDataFrame):
    """Generate spectrally unmix ratio images.

    Parameters
    ----------
    reference_spectra : list, ndarray, References object
        List, array, or References object of reference spectra for linear
        spectral unmixing.
    background : string
        Background key label.
        Defaults to 'bkg'.

    """

    def __init__(self, reference_spectra, background='bkg'):
        super(Ratio, self).__init__()
        self.reference_spectra = reference_spectra
        self.background = background
        self.spec_unmix = SpectralUnmixing(reference_spectra)

    def get(self, image_sets, reference, combine_data=None):
        """Calculate unmixed and ratio images.

        Parameters
        ----------
        image_set : Xarray DataArray, mblres ImageDataFrame
            These are the images (emission channels) to be unmixed.
        reference : string
            Reference key label, e.g. 'Eu', used for ratio images.
        comb_data : Xarray DataArray, mblres ImageDataFrame
            These are the images that are combined with 'image_set'.
            Must be same dimensions and type as 'image_set'.

        """
        if isinstance(image_sets, dict):
            self._dataframe = self._find_multi_set(image_sets, reference)
        else:
            self._dataframe = self._return_data(image_sets, reference)
        if combine_data is not None:
            self.combine(combine_data)

    def _find_multi_set(self, image_sets, reference):
        sets = list(image_sets.keys())
        data = [self._return_data(image_sets[s], reference)
                for s in sets]
        result = {
            sets[idx]: value for idx, value in enumerate(data)
        }
        return result

    def _return_data(self, images, reference):
        self.spec_unmix.unmix(images)
        unmix_images = self.spec_unmix.data
        channels = ImageDataFrame.get_dim_names(unmix_images, set_dim='c')
        channels.remove(reference)
        if self.background in channels:
            channels.remove(self.background)
        ratio_images = unmix_images.loc[dict(c=channels)] / \
            unmix_images.loc[dict(c=reference)]
        ratio_images.coords['c'] = [s + '_ratio' for s in channels]
        result = xr.concat([unmix_images, ratio_images], dim='c')
        return result


class Extract(TableDataFrame):
    """Extract data from images using masks.

    Parameters
    ----------
    function : function
        This is the function used to extract data from each bead region. This
        can be replaced with any 1 parameter function, e.g. np.mean.
        Defaults to np.median.

    """

    def __init__(self, function=None):
        super(Extract, self).__init__()
        if function is None:
            self._func = np.median
        else:
            self._func = function
        self._dataframe = None
        self.flag_filt = True

    def get(self, images, masks, combine_data=None):
        """Extract data from images using masks.

        Parameters
        ----------
        images : Xarray DataArray, mrbles ImageDataFrame
            Images of which to take values from using provided labeled masks.
            Must be same number of dimensions as masks.
        masks : Xarray DataArray, mrbles ImageDataFrame
            Labeled mask of regions to take values from the provided images.
            Must be same number of dimensions as images, even if one dimension
            is only singular. Therefore, use [] around mask selection, even
            when only using a single channel: ['inside'].

        Examples
        --------
        >>> per_mrble_data = mrbles.Extract(np.median)
        >>> per_mrble_data.run(images['100  nM', :, ['Cy5', 'Cy3']],
                               masks['100 nM', :, ['ring']])
        >>> per_mrble_data.data

        """
        if isinstance(images, xr.DataArray):
            if images.ndim == 4:
                f_list = ImageDataFrame.get_dim_names(
                    images, set_dim=images.dims[0])
                data = [self._get_data_images(images.loc[f], masks.loc[f])
                        for f in f_list]
                self._dataframe = pd.concat(data, keys=f_list)
            else:
                self._dataframe = pd.DataFrame(
                    self._get_data_images(images, masks))
        else:
            data_append = []
            s_list = list(images.keys())
            for set_x in s_list:
                f_list = ImageDataFrame.get_dim_names(
                    images[set_x], set_dim=images[set_x].dims[0])
                data = [self._get_data_images(images[set_x][f],
                                              masks[set_x][f])
                        for f in f_list]
                data_append.append(pd.concat(data, keys=f_list))
            self._dataframe = pd.concat(data_append, keys=s_list)
        self._dataframe[self.flag_name] = False
        if len(self._dataframe.index.names) == 3:
            self._dataframe.index.rename(
                ['set', 'file', 'bead_index'], inplace=True)
        else:
            self._dataframe.index.rename(['f', 'bead_no'], inplace=True)
        if combine_data is not None:
            self.combine(combine_data)
        self._dataframe.reset_index(inplace=True)

    def _get_data_images(self, images, masks):
        data = {
            str(image[images.dims[0]].values):
            self._get_data_masks(image, masks, self._func)
            for image in images
        }
        data_flatten = self._flatten_dict(data, prefix='.')
        dataframe = pd.DataFrame.from_dict(data_flatten, orient='columns')
        return dataframe

    @classmethod
    def _get_data_masks(cls, image, masks, func):
        if masks.ndim == 3:
            idx = cls._get_index(masks[0])
        else:
            idx = cls._get_index(masks)
        if idx is None:
            data = [None]
        else:
            if masks.ndim == 3:
                data = {
                    str(mask[masks.dims[0]].values):
                    cls._get_data(image, mask, func, idx)
                    for mask in masks
                }
            else:
                data = {
                    str(masks[masks.dims[0]].values):
                    cls._get_data(image, masks, func, idx)
                }
            data['mask_lbl'] = idx
        return data

    @classmethod
    def _get_data(cls, image, mask, func, idx):
        # idx = cls._get_index(mask)
        if idx is None:
            data = [None]
        else:
            data = ndi.labeled_comprehension(image,
                                             mask,
                                             idx,
                                             func,
                                             float,
                                             None)
        return data

    @staticmethod
    def _get_index(mask):
        if np.count_nonzero(mask) == 0:
            num = None
        else:
            num = np.unique(mask.values[mask.values > 0])
        return num

    def filter(self, bkg_factor=2.0, ref_factor=2.0,
               bkg='bkg.mask_full', ref='Eu.mask_inside'):
        """Filter and flag based on unmixed background and reference signal.

        Parameters
        ----------
        bkg_factor : float
            Filter factor of Standard Deviations away from mean background
            signal.
            Defaults to 2.0
        ref_factor : float
            Filter factor of Standard Deviations within mean of reference
            signal.
            Defaults to 2.0
        bkg : string
            Background signal column name.
            Defaults to 'bkg.mask_full'
        ref : string
            Reference signal column name.
            Defaults to 'Eu.mask_inside'

        """
        bkg_data = self._dataframe[bkg]
        bkg_mean = bkg_data.mean()
        bkg_sd = bkg_data.std()
        mask_bkg = ((bkg_data > (bkg_mean - bkg_factor * bkg_sd)) &
                    (bkg_data < (bkg_mean + bkg_factor * bkg_sd)))
        ref_data = self._dataframe[ref]
        ref_mean = ref_data.mean()
        ref_sd = ref_data.std()
        mask_ref = ((ref_data > (ref_mean - ref_factor * ref_sd)) &
                    (ref_data < (ref_mean + ref_factor * ref_sd)))
        filter_all = (mask_bkg & mask_ref)
        self._dataframe[self.flag_name] = ~filter_all
        num_out = len(self._dataframe[self._dataframe.flag == True])  # NOQA
        num_remain = len(self._dataframe[self._dataframe.flag == False])  # NOQA
        num_total = len(self._dataframe)
        num_percentage = ((num_out / num_total) * 100)
        print("Pre-filter: %i" % num_total)
        print("Post-filter: %i" % num_remain)
        print("Filtered: %i (%0.1f%%)" % (num_out, num_percentage))


class Decode(TableDataFrame):
    """Decode MRBLEs.

    Parameters
    ----------
    target : list
        List of target ratios
    seq_list : Pandas DataFrame
        Columns with sequence information.
        Defaults to None.
    decode_channels : list
        Channel names.
        Defaults to None.

    """

    def __init__(self, target, seq_list=None, decode_channels=None):
        super(Decode, self).__init__()
        self._target = target
        self._decode_channels = decode_channels
        self.seq_list = seq_list
        # Instantiate ICP and GMM with default settings
        self._icp = ICP(target)
        self._gmm = Classify(target)
        self._dataframe = None
        self._cluster_check = None
        # Setup settings object
        self.settings = Settings([self._icp, self._gmm], ['icp', 'gmm'])
        self.settings.__doc__ = """
            Return Decode object for settings purposes.

            See ICP and Classify documentation for detailed settings."""

    def decode(self, data, combine_data=None):
        """Decode MRBLEs.

        Parameters
        ----------
        data : Pandas DataFrame
            Data that contains decoding data.
        combine_data : Pandas DataFrame
            Data to be combined from previous pipeline steps.
            Defaults to None.

        """
        if self._decode_channels is not None:
            pass
        self._icp.fit(data)
        icp_data = self._icp.transform()
        self._gmm.decode(icp_data)
        self._gmm_qc(data)
        self._dataframe = self._gmm.output
        if self.seq_list is not None:
            self._dataframe = self._add_info(self.seq_list, self._dataframe)
        self._dataframe = self._dataframe.combine_first(icp_data)
        if combine_data is not None:
            self.combine(combine_data)
        self._cluster_check = ClusterCheck(self)

    def plot_clusters_3D(self, confidence=None):
        """Plot ratio clusters in 3D.

        Parameters
        ----------
        confidence : float
            Set minimal confidence level.
            Defaults to None.
        """
        self._cluster_check.plot_3D(confidence)

    def plot_clusters_2D(self, colors, ci_trace=None, confidence=None):
        """Plot ratio clusters in 2D.

        Parameters
        ----------
        colors : list
            List of color (NPL) names.
        ci_trace : float
            Set trace confidence line around clusters.
            Defaults to None.
        confidence : float
            Set minimal confidence level of data.
            Defaults to None.
        """
        self._cluster_check.plot_2D(colors, ci_trace, confidence)

    def _gmm_qc(self, data):
        print("Number of unique codes found:", self._gmm.found)
        print("Missing codes:", self._gmm.missing)
        s_score = silhouette_score(data, self._gmm.output.code)
        print("Silhouette Coefficient:", s_score)
        # print("AIC:", self._gmm._gmix.aic(data))
        # print("BIC:", self._gmm._gmix.bic(data))


class Analyze(TableDataFrame):
    """Analyze data MRBLE data and retutn per-code statistics.

    Parameters
    ----------
    seq_list : list, Pandas DataFrame
        List (one column) or Pandas DataFrame with additional per-code
        information. In the case of a Pandas DataFrame all provided columns
        will be added, based on the row number, which corresponds to its code.
    flag_filt : boolean
        Sets if the flagged data is automatically filtered out.
        Defaults to True.

    Attributes
    ----------
    functions : dict
        Dictionary of functions and their corresponding names.
        Default: {'mean': np.mean,
                  'median': np.median,
                  'sd': np.std,
                  'se': sp.stats.sem,
                  'N': len,
                  'CV': sp.stats.variation}

    """

    def __init__(self, dataframe, seq_list=None, images=None):
        super(Analyze, self).__init__()
        self.seq_list = seq_list
        self._images = images
        self._data_per_bead = dataframe
        self._norm_data = None

        # Attributes
        self.flag_filt = True
        self.functions = {  # Default set of functions
            'mean': np.mean,
            'median': np.median,
            'sd': np.std,
            'se': sp.stats.sem,
            'N': len,
            'CV': sp.stats.variation
        }
        # Analyze per-code
        self._dataframe = self._analyze(dataframe)

    def _analyze(self, data):
        if 'set' in data.columns:
            return self._multi(data)
        else:
            return self._single(data)

    def background(self, bkg_data):
        """Subtract background.

        Parameters
        ----------
        bkg_data : float/int, string, list, NumPy array, Pandas DataFrame
            If float/value is used, this value be subtracted. If string is
            used, column from internal dataframe is used. Otherwise, the data
            is subtracted, which needs to be the same size as the per-bead
            data. In the case of Pandas DataFrame, do slice the single exact
            column. Row number of the data is the code.

        """
        pass

    def normalize(self, norm_data, scaled=True):
        """Normalize data.

        Parameters
        ----------
        norm_data : Pandas DataFrame
            Dataframe with the per-bead normalization data. Single set only!
        scaled : boolean
            Scale maximum value normalization data to 1.
            Defaults to True.

        """
        per_code = self._single(norm_data)
        if scaled is True:
            per_code['mean_scaled'] = per_code['mean'] / per_code['mean'].max()
            per_code['median_scaled'] = per_code['median'] / per_code['median'].max()
            per_code['sd_scaled'] = per_code['sd'] / per_code['mean'].max()
            per_code['se_scaled'] = per_code['sd_scaled'] / np.sqrt(per_code['N'])
        self._norm_data = per_code
        set_codes = np.unique(beads_data['code'])
        for code in set_codes:
            if scaled is True:
                norm_mean = per_code.loc[per_code['code'] == code, 'mean_scaled'].values
                norm_sd = per_code.loc[per_code['code'] == code, 'sd_scaled'].values
            else:
                norm_mean = per_code.loc[per_code['code'] == code, 'mean'].values
                norm_sd = per_code.loc[per_code['code'] == code, 'sd'].values

            data_mean = self._dataframe.loc[self._dataframe['code'] == code, 'mean'].values
            data_median = self._dataframe.loc[self._dataframe['code'] == code, 'median'].values
            data_sd = self._dataframe.loc[self._dataframe['code'] == code, 'sd'].values
            data_n = self._dataframe.loc[self._dataframe['code'] == code, 'N'].values

            mean_norm = (data_mean / norm_mean)
            median_norm = (data_median / norm_mean)
            sd_norm = np.abs(mean_norm) * (np.sqrt((data_sd / data_mean) ** 2 + (norm_sd / norm_mean)**2))
            cv_norm = mean_norm / sd_norm
            se_norm = sd_norm / np.sqrt(data_n)

            self._dataframe.loc[self._dataframe['code'] == code, 'mean_norm'] = mean_norm
            self._dataframe.loc[self._dataframe['code'] == code, 'median_norm'] = median_norm
            self._dataframe.loc[self._dataframe['code'] == code, 'sd_norm'] = sd_norm
            self._dataframe.loc[self._dataframe['code'] == code, 'cv_norm'] = cv_norm
            self._dataframe.loc[self._dataframe['code'] == code, 'se_norm'] = se_norm

    @property
    def norm_data(self):
        return self._norm_data

    @property
    def data_per_bead(self):
        """Return (normalized) data per bead."""
        return self._data_per_bead

    def _single(self, data):
        channels = list(data.columns)
        channels.remove('code')
        if self.flag_name in channels:
            channels.remove(self.flag_name)
        if 'set' in channels:
            channels.remove('set')
        codes = np.unique(data.code.values).astype(int)
        result = {}
        for code in codes:
            for channel in channels:
                result[code] = self._iter_functions(
                    self.functions, data.loc[(data.code == code), channel])
        dataframe = pd.DataFrame.from_dict(result, orient='index')
        dataframe.index.rename('code', inplace=True)
        if self.seq_list is not None:
            dataframe = self._add_info(self.seq_list, dataframe, codes=codes)
        return dataframe

    def _multi(self, data):
        levels = list(np.unique(data.set))
        # levels.remove('set')
        result = [
            self._single(data.loc[data.set == level]) for level in levels
        ]
        dataframe = pd.concat(result, keys=levels)
        dataframe.index.rename(('set', 'code'), inplace=True)
        return dataframe.reset_index()

    def _norm_per_code(self):
        pass

    def _norm_per_bead(self):
        pass

    @staticmethod
    def _iter_functions(functions, data):
        data_na_omit = data.values[~np.isnan(data.values)]
        result = {
            key: func(data_na_omit) for (key, func) in functions.items()
        }
        return result

    def per_mrble_report(self):
        """Generate per-MRBLE PDF image report."""
        pass

    def qc_report(self):
        """Generate Quality Control PDF report."""
        pass


# Deprecated
def get_stats_per_channel_and_code(data, channels, codes=None):
    """Get stats per channel and code."""
    bead_sets = []
    for channel in channels:
        bead_sets.append(get_stats_per_code(data, channel, codes))
    final_bead_set = pd.concat(bead_sets, keys=channels)
    return final_bead_set


def get_stats_per_code(data, channel,
                       norm=None, norm_channel=None, codes=None):
    """Get statistical values for each code in you data set.

    Parameters
    ----------
    data : Pandas DataFrame
        This is the per bead data.
    channel : string
        This is the channel (or column) to extract statistical values from.
    codes : int, list
        This value can be set if only a select (list) or one code (int) needs
        to be processed. If value is not set the unique codes from data, the
        Pandas DataFrame is used.
        Defaults to None.

    Returns
    -------
    bead_set : Pandas DataFrame
        This dataframe contains: AVG, SD, N, CV, SEM, and RSEM for each code.
        Codes start at 0. Code -1 represents weighted statistical values over
        all codes.

    """
    data_stats = []
    data_stats_norm = []
    n_codes = []
    if isinstance(codes, list):
        codes_set = codes
    elif (isinstance(data, pd.DataFrame)) and (codes is None):
        codes_set = np.unique(data.code[data.code.notnull()])
    else:
        codes_set = range(codes)
    for code in codes_set:
        n_codes.append(code)
        data_code = data.loc[data.code == code, (channel)]
        stats = get_stats(data_code)
        data_stats.append(stats)
        if norm is not None:
            if norm_channel is not None:
                norm_code = norm.loc[norm.code == code, (norm_channel)]
            else:
                norm_code = norm.loc[norm.code == code, (channel)]
            stats_norm = get_stats_norm(data_code, norm_code)
            data_stats_norm.append(stats_norm)
    # n_codes.append(-1)
    # data_stats.append(get_weighted_stats(data_stats))
    final_codes = pd.DataFrame(n_codes, columns=['code'])
    final_stats = pd.DataFrame(
        data_stats, columns=['AVG', 'SD', 'N', 'CV', 'SEM', 'RSEM', 'MED'])
    if norm is not None:
        # data_stats_norm.append(get_weighted_stats(data_stats_norm))
        final_stats_norm = pd.DataFrame(data_stats_norm,
                                        columns=['AVG_NORM',
                                                 'SD_NORM',
                                                 'N_NORM',
                                                 'CV_NORM',
                                                 'SEM_NORM',
                                                 'RSEM_NORM',
                                                 'MED_NORM'])
    bead_set = final_codes.join(final_stats)
    if norm is not None:
        bead_set = bead_set.join(final_stats_norm)
    return bead_set


def get_stats_norm(data, norm, scale_norm=True):
    if scale_norm is True:
        norm /= norm.max()
    norm_mean = np.nanmean(norm)
    norm_sd = np.nanstd(norm)
    data_mean = np.nanmean(data)
    data_sd = np.nanstd(data)

    mean = data_mean / norm_mean
    sd = np.abs(mean) * (np.sqrt((data_sd / data_mean) ** 2 +
                                 (norm_sd / norm_mean)**2))
    n = len(data)
    cv = sd / mean
    sem = sd / sqrt(n)
    rsem = sem / mean
    median = np.nanmedian(data / norm_mean)
    return np.array([mean, sd, n, cv, sem, rsem, median])


def get_stats(data_array):
    """Get statistics from data.

    Parameters
    ----------
    data_array :

    Returns
    -------
    stats_array

    """
    data_mean = np.nanmean(data_array)
    data_median = np.nanmedian(data_array)
    data_sd = np.nanstd(data_array)
    data_n = len(data_array)
    data_cv = data_sd / data_mean
    data_sem = data_sd / sqrt(data_n)
    data_rsem = data_sem / data_mean
    stats_array = np.array([data_mean,
                            data_sd,
                            data_n,
                            data_cv,
                            data_sem,
                            data_rsem,
                            data_median])
    return stats_array


def get_weighted_stats(data_array):
    """Get weighted statistics.

    Parameters
    ----------
    data_array : NumPy array, list
        Array with data to return statistics from.

    Returns
    -------
    NumPy array
        Returns array with weighted stats over

    """
    data_mean = np.average(data_array[:, 0], weights=data_array[:, 2])
    data_sd = sqrt(np.average(
        (data_array[:, 0] - data_mean) ** 2, weights=data_array[:, 2]))
    data_n = np.sum(data_array[:, 2])
    data_cv = data_sd / data_mean
    data_sem = data_sd / sqrt(data_n)
    data_rsem = data_sem / data_mean
    data_median = ws.weighted_median(np.nan_to_num(
        data_array[:, 0]), weights=np.nan_to_num(data_array[:, 2]))
    return np.array([data_mean,
                     data_sd,
                     data_n,
                     data_cv,
                     data_sem,
                     data_rsem,
                     data_median])
