# !/usr/bin/env python

# [Future imports]
# "print" function compatibility between Python 2.x and 3.x
from __future__ import print_function
# Use Python 3.x "/" for division in Pyhton 2.x
from __future__ import division

# [File header]     | Copy and edit for each file in this project!
# title             : general.py
# description       : Bead Kinetics module
# author            : Bjorn Harink
# credits           : Kurt Thorn, Huy Nguyen
# date              : 20160308
# version update    : 20160808
# version           : v0.4
# usage             : As module
# notes             : Do not quick fix functions for specific needs, keep them general!
# python_version    : 2.7

# [Main header with project metadata] | Only in the main file!
# Copyright and credits
__copyright__   = ("Copyright 2016 - "
                   "The Encoded Beads Project - "
                   "ThornLab@UCSF and "
                   "FordyceLab@Stanford")
# Original author(s) of this Python project, like: ("...", 
__author__      = ("Bjorn Harink")  #        "name")
# People who contributed to this Python project, like: ["...",
__credits__     = ["Kurt Thorn",  #              "name"] 
                   "Huy Nguyen"]
# Maintainer contact information
__maintainer__  = "Bjorn Harink" 
__email__       = "bjorn@harink.info" 
# Software information
__license__     = "MIT" 
__version__     = "v0.3"
__status__      = "Prototype"

# [TO-DO]

# [Modules]
# General
import sys
import re
import os
import glob
import types
import warnings
# Math
from math import sqrt
import numpy as np
import pandas as pd
# Image import
import bioformats as bf
from bioformats import log4j
import javabridge as jb  # Used for bioformats
import fnmatch
# Image processing
import cv2
from scipy import ndimage as ndi
import sklearn
from sklearn import metrics
from sklearn import mixture
from sklearn import preprocessing
#from skimage import img_as_ubyte
from skimage.feature import peak_local_max
from skimage.morphology import watershed
from skimage.external import tifffile as tff
# Image display
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d import axes3d
# File processing
from sklearn.externals import joblib
from sklearn import linear_model
import statsmodels.api as sm
# Project
import bead_analysis.data as ba

# TO-DO
# Check error exceptions
# Create error checking functions for clustering
# Update filterObjects

# TO-DO: UPDATE
def filterObjects(data, back, reference, objects_radius, back_std_factor=3, reference_std_factor=2, radius_min=3, radius_max=6):
    """Filter Objects
    Filter objects using x times SD from mean
    back = background data
    reference = reference data
    back_std_factor = x times SD from mean
    reference_std_factor = x times SD from mean
    """
    # Pre-filtered number
    pre_filter_no = data[:, 0].size

    # Mean and standard deviation of the background and the reference channel
    mean_reference = np.mean(reference)
    std_reference = np.std(reference)
    mean_back = np.mean(back)
    std_back = np.std(back)
    print(mean_reference, std_reference, mean_back, std_back)

    # Find indices of objects within search parameters
    # Check which objects are within set radius
    size_filter = np.logical_and(
        objects_radius >= radius_min, objects_radius <= radius_max)
    # Check which objects are within x SD from mean background signal
    back_filter = np.logical_and(back < (mean_back + back_std_factor * std_back),
                                 back > (mean_back - back_std_factor * std_back))
    # Check which objects are within x SD from mean reference signal
    refr_filter = np.logical_and(reference > (mean_reference - reference_std_factor * std_reference),
                                 reference < (mean_reference + reference_std_factor * std_reference))
    # Create list of indices of filtered-in objects
    filter_list = np.argwhere(np.logical_and(
        size_filter, np.logical_and(back_filter, refr_filter)))[:, 0]

    # Compare pre and post filtering object numbers
    post_filter_no = filter_list.size
    post_filter_per = int(
        ((pre_filter_no - post_filter_no) / post_filter_no) * 100)
    print("Pre-filter no:", pre_filter_no, ", Post-filter no:",
          post_filter_no, ", Filtered:", post_filter_per, "%")

    # Return list of indices of filtered-in objects
    return filter_list


class FindBeads(object):
    """Find and identify bead objects from image.
    """
    def __init__(self, min_r=1, max_r=10, param_1=10, param_2=10, annulus_width = 2, min_dist = None, enlarge = 1):
        self.min_r = min_r
        self.max_r = max_r
        self.annulus_width = annulus_width
        self.param_1 = param_1
        self.param_2 = param_2
        self.enlarge = enlarge
        # TO-DO proper method
        if min_dist is not None:
            self.min_dist = min_dist
        else:
            self.min_dist = 2*min_r
        self._labeled_mask = None
        self._labeled_annulus_mask = None
        self._circles_dim = None

    @property
    def labeled_mask(self):
        return self._labeled_mask

    @property
    def labeled_annulus_mask(self):
        return self._labeled_annulus_mask

    @property
    def circles_dim(self):
        return self._circles_dim

    @staticmethod
    def convert(image):
        """8 Bit Convert
        Checks image data type and converts if necessary to uint8 array.
        image = M x N image array
        """
        try:
            img_type = image.dtype
        except ValueError:
            print("Not a NumPy array of image: %s" % image)
        except:
            print("Unexpected error:", sys.exc_info())
        else:
            if img_type == 'uint16':
                image = np.array( ((image / 2**16) * 2**8), dtype='uint8')
        finally:
            return image

    @staticmethod
    def circle_mask(image, min_dist, min_r, max_r, param_1, param_2, enlarge):
        """Make Circle Mask
        """
        # Find initial circles using Hough transform
        circles = cv2.HoughCircles(image, cv2.HOUGH_GRADIENT, dp=1,  
                                   minDist=min_dist, 
                                   param1=param_1, 
                                   param2=param_2, 
                                   minRadius=min_r, 
                                   maxRadius=max_r)[0]
        # Make mask
        mask = np.zeros(image.shape, np.uint8)
        for c in circles:
            x, y, r = c[0], c[1], int(np.ceil(c[2]*enlarge))
            # Draw circle (line width -1 fills circle)
            cv2.circle(mask, (x, y), r, (255, 255, 255), -1)
        return mask

    @staticmethod
    def circle_separate(mask):
        """Circle Separate
        """
        # Find and separate circles using watershed on initial mask
        D = ndi.distance_transform_edt(mask)
        localMax = peak_local_max(D, indices=False, 
                                  min_distance=1, 
                                  exclude_border=True, 
                                  labels=mask)
        markers = ndi.label(localMax, structure=np.ones((3, 3)))[0]
        labels = watershed(-D, markers, mask=mask)
        print("Number of unique segments found: {}".format(
            len(np.unique(labels)) - 1))
        return labels

    def _get_dimensions(self, labels):
        """
        Find center of circle and return dimensions
        """
        idx = np.arange(1, len(np.unique(labels)))
        circles_dim = np.empty((len(np.unique(labels)) - 1, 3))
        for label in idx:
            # Create single object mask
            mask_detect = np.zeros(labels.shape, dtype="uint8")
            mask_detect[labels == label] = 255
            # Detect contours in the mask and grab the largest one
            cnts = cv2.findContours(mask_detect.copy(), 
                                    cv2.RETR_EXTERNAL, 
                                    cv2.CHAIN_APPROX_SIMPLE)[-2]
            c = max(cnts, key=cv2.contourArea)
            # Get circle dimensions
            ((x, y), r) = cv2.minEnclosingCircle(c)
            circles_dim[label - 1, 0] = x
            circles_dim[label - 1, 1] = y
            circles_dim[label - 1, 2] = r
        return circles_dim

    def find(self, image):
        """Find Objects
        Find objects in image and return data
        """
        img = self.convert(image)
        # Find initial circles using Hough transform and make mask
        mask = self.circle_mask(img, self.min_dist, 
                                     self.min_r, 
                                     self.max_r, 
                                     self.param_1, 
                                     self.param_2,
                                     self.enlarge)
        # Find and separate circles using watershed on initial mask
        self._labeled_mask = self.circle_separate(mask)
        # Find center of circle and return dimensions
        self._circles_dim = self._get_dimensions(self._labeled_mask)
        
        # Create annulus mask
        self._labeled_annulus_mask = self._labeled_mask.copy()
        for cd in self._circles_dim:
            if (int(cd[2] - self.annulus_width)) < ((self.min_r+1) - self.annulus_width): 
                r_dim = 1
            else:
                r_dim = int(cd[2] - self.annulus_width)
            cv2.circle(self._labeled_annulus_mask, 
                       (int(cd[0]), int(cd[1])), r_dim, 
                       (0, 0, 0), -1)

    def overlay_image(self, image, annulus=None, dim=None):
        """Overlay Image
        Overlay image with circles of labeled mask
        """
        img = image.copy()
        if dim is not None:
            circ_dim = dim
        else:
            circ_dim = self._circles_dim
        for dim in circ_dim:
            if annulus is not None and annulus > 0:
                if (int(dim[2] - self.annulus_width)) < ((self.min_r+1) - self.annulus_width): 
                    r_dim = 1
                else:
                    r_dim = int(dim[2] - self.annulus_width)
                cv2.circle(img, (int(dim[0]), int(dim[1])), r_dim, (0, 255, 0), 1)
            cv2.circle(img, (int(dim[0]), int(dim[1])), int(dim[2]), (0, 255, 0), 1)
        return img

# DEPRECRATED
#class RefSpec(object):
#    """Reference Spectra
#    Generate reference spectra
#    """
#    def __init__(self, image_files, crop = [100, 400, 100, 400], size_param = [1, 9, 10, 10, 7, 10]):
#        self.image_files = image_files
#        self.crop = crop
#        self.ref_spec_set = None
#        self.objects = None
#        self.size_param = size_param

#    def __close__(self):
#        """Destructor of RefSpec"""
#        return 0

#    def readSpectra(self):
#        """Read Spectra
#        """
#        ref_spec_set = np.array( [self.readSpectrum(file, 0,  self.size_param[idx], crop = self.crop) for idx, file in enumerate(self.image_files)] )
#        self.ref_spec_set = ref_spec_set
#        return ref_spec_set.T

#    def readSpectrum(self, file, object_channel, size_param = [3, 9, 10, 10, 7, 10], crop = None):
#        """Read Spectrum
#        """
#        if size_param is None:
#            size_param = [3, 9, 10, 10, 7, 10]
#        if crop == None: crop = self.crop
#        ref_set = ImageSet(file)
#        ref_set_data = ref_set.readSet()[:, crop[0]:crop[1], crop[2]:crop[3]]
#        objects = self.getRefObjects(ref_set_data[object_channel], 
#                                     sep_min_dist=size_param[0], min_dist=size_param[1], 
#                                     param_1=size_param[2], param_2=size_param[3], 
#                                     min_r=size_param[4], max_r=size_param[5])
#        channels = range(ref_set_data[:, 0, 0].size)
#        channels.remove(object_channel)
#        ref_data = self.getRef(ref_set_data[channels])
#        return ref_data

#    def getRefObjects(self, object_image, sep_min_dist=3, min_dist=9, param_1=10, param_2=10, min_r=7, max_r=10):
#        """Get Reference Objects
#        """
#        objects = Objects(object_image)
#        labels, labels_annulus, circles_dim = objects.findObjects(
#            sep_min_dist=sep_min_dist, min_dist=min_dist, 
#            param_1=param_1, param_2=param_2, min_r=min_r, max_r=max_r)
#        self.objects = labels
#        return labels

#    def getRef(self, image_data, back = 451):
#        """Get Reference
#        Get reference spectra from image set
#        """
#        channels = range(image_data[:, 0, 0].size)
#        ref_data = np.array( [self.getMedianObjects(image_data[ch], self.objects) for ch in channels], dtype="float64" )
#        ref_data = ref_data - back
#        sum = ref_data.sum()
#        return np.divide(ref_data, sum)

#    def getMedianObjects(self, image_data, objects):
#        """Get Median Objects"""
#        data = ndi.median(image_data, objects)
#        return data

#    def getBack(image_data, square):
#        """Get Background
#        Get background reference of specified area
#        image_data = single image used for background
#        square = coordinates of region of interest [Y1, Y2, X1, X2]
#        """
#        c_size = image_data[:, 0, 0].size - 1
#        channels = xrange(1, c_size + 1)
#        ref_data = np.empty((c_size), dtype="float64")
#        for ch in channels:
#            img_tmp = image_data[ch, square[0]:square[1], square[2]:square[3]]
#            ref_data[ch - 1] = np.median(img_tmp)
#        sum = ref_data.sum()
#        return np.divide(ref_data, sum)

class SpectralUnmixing(ba.FrozenClass):
    """Spectral Unmix
    
    Unmix the spectral images to dye images, e.g., 620nm, 630nm, 650nm images to Dy, Sm and Tm nanophospohorous lanthanides using reference spectra for each dye.
    ref_data = Reference spectra for each dye channel as Numpy Array: N x M, where N are the spectral channels and M the dye channels 
    image_data = Spectral images as NumPy array: N x M x P, where N are the spectral channels and M x P the image pixels (Y x X)
    """
    def __init__(self, ref_data, names=None):
        if isinstance(ref_data, ba.Spectra):
            self._ref_object = ref_data
            self._ref_data = ref_data.ndata
            self._names = ref_data.spec_names
        elif isinstance(ref_data, np.ndarray):
            self._ref_data = ref_data
            if self._names is None:
                self._names = range(len(self._ref_data[0,:]))
        else:
            raise TypeError("Wrong type. Only Bead-Analysis Spectra or Numpy ndarray types.")
        self._dataframe = pd.Panel(items=self._names)
        #self._freeze()

    def __repr__(self):
        """Returns Pandas dataframe representation.
        """
        return repr([self._dataframe])

    def __getitem__(self, index):
        """Get method, see method 'spec_get'.
        """
        return self._dataframe.ix[index].values

    def unmix(self, images):
        """Unmix
        Unmix the spectral images to dye images, e.g., 620nm, 630nm, 650nm images to Dy, Sm and Tm nanophospohorous lanthanides using reference spectra for each dye.
        ref_data = Reference spectra for each dye channel as Numpy Array: N x M, where N are the spectral channels and M the dye channels 
        image_data = Spectral images as NumPy array: N x M x P, where N are the spectral channels and M x P the image pixels (Y x X)
        """
        # Check if inputs are NumPy arrays and check if arrays have equal channel sizes
        self._ref_size = self._ref_data[0, :].size
        self._c_size = images[:, 0, 0].size
        self._y_size = images[0, :, 0].size
        self._x_size = images[0, 0, :].size
        if self._ref_data.shape[0] != images.shape[0]:
            print("Number of channels not equal. Ref: ", ref_shape, " Image: ", img_shape)
            raise IndexError
        img_flat = self._flatten(images)
        unmix_flat = np.linalg.lstsq(self._ref_data, img_flat)[0]
        unmix_result = self._rebuilt(unmix_flat)
        # TO-DO Change to proper insert
        self._dataframe = pd.Panel(unmix_result, items=self._names)
    
    @property
    def pdata(self):
        return self._dataframe
    @property
    def ndata(self):
        return self._dataframe.values

    def _flatten(self, images):
        """Flatten
        Flatten X and Y of images in NumPy array
        """
        images_flat = images.reshape(self._c_size, (self._y_size * self._x_size))
        return images_flat

    def _rebuilt(self, images_flat):
        """Rebuilt
        Rebuilt images to NumPy array
        """
        images = images_flat.reshape(self._ref_size, self._y_size, self._x_size)
        return images

class ICP(object):
    """Iterative Closest Point (ICP) algorithm to minimize the difference between two clouds of points.

    Parameters
    ----------
    matrix_method : string/function/list, optional
        Transformation matrix method. Standard methods: 'max', 'mean', 'min', 'std'. 
        Other options: own function or list of initial guesses. 
        Defaults to 'max'.

    max_iter : int, optional
        Maximum number of iterations. 
        Defaults to 100.

    tol : float, optional
        Convergence threshold. ICP will stop after delta < tol.
        Defaults to 1e-4.

    outlier_pct : float, optional
        Discard percentile 0.x of furthest distance from target. Percentile given in fraction [0-1], e.g. '0.001'.
        Defaults to 0.

    Attributes
    ----------
    matrix : NumPy array
        This stores the transformation matrix.

    offset : NumPy vector
        This stores the offset vector.

    Functions
    ---------
    fit : function
        Function to find ICP using set parameters and attributes.

    transform : function
        Function to apply transformat data using current transformation matrix and offset vector.
    """
    def __init__(self, matrix_method='max', max_iter=100, tol=1e-4, outlier_pct = 0):
        self.matrix, self.matrix_func = self._set_matrix_method(matrix_method)
        self.max_iter = max_iter
        self.tol = tol
        self.outlierpct = outlier_pct
        self.offset = None

    def _set_matrix_method(self, matrix_method):
        """Set matrix method
        """
        matrix = None
        if matrix_method == 'max':
            matrix_func = np.max
        elif matrix_method == 'mean':
            matrix_func = np.mean
        elif matrix_method == 'min':
            matrix_func = np.min
        elif matrix_method == 'std':
            matrix_func = np.std
        elif isinstance(matrix_method, types.FunctionType):  # Use own or other function
            matrix_func = matrix_method
        elif isinstance(matrix_method, types.ListType):  # Use list of initial ratios
            matrix_func = matrix_method
            naxes = len(matrix_method)
            matrix = np.eye(naxes)
            for n in xrange(naxes):
                matrix[n, n] = matrix_method[n]
        else:
            raise ValueError("Matrix method invalid: %s" % matrix_method)
        return matrix, matrix_func

    @staticmethod
    def matrix_create(func, input1, input2):
        """Matrix Create
        Create identity matrix and set values with function on inputs e.g np.mean
        naxes = number
        func = function
        input1 = matrix 1
        input2 = matrix 2
        """
        naxes1 = len(input1[0, :])
        naxes2 = len(input2[0, :])
        if naxes1 == naxes2:
            matrix = np.eye(naxes1)
            for n in xrange(naxes1):
                matrix[n, n] = func(input1[:,n]) / func(input2[:,n])
        else:
            raise ValueError("Lengths of input1 = %s and input2 = %s do not match", naxes1, naxes2)
        return matrix

    def transform(self, data):
        result = np.dot(data, self.matrix) + self.offset
        return result

    def fit(self, data, target):
        """ICP
        Iterative Closest Point
        """
        if self.offset is None:
            self.offset = self._set_offset(data, target)

        if self.matrix is None:
            self.matrix = self._set_matrix(data, target)
        
        weights = list(range(1, len(data[:,0])+1))
        delta = 1
        for i in xrange(self.max_iter):
            if delta < self.tol:
                print("Converged after:", i)
                break

            # Copy old to compare to new
            matrix_old = self.matrix
            offset_old = self.offset

            # Apply transform
            data_transform = self.transform(data)

            # Compare distances between tranformed data and target
            distances = metrics.pairwise.pairwise_distances(data_transform, target)
            min_dist = np.min(distances, axis=1)
            min_dist_pct = np.percentile(min_dist, [0, (1-self.outlierpct)*100])[1]
            min_dist_filt = np.argwhere(min_dist < min_dist_pct)[:, 0]
            matched_code = np.argmin(distances, axis=1)
            matched_levels = target[matched_code[min_dist_filt], :]
            d = np.c_[data[min_dist_filt], np.ones(len(data[min_dist_filt, 0]))]
            m = np.linalg.lstsq(d, matched_levels)[0]
            
            ### TEST Weighted ICP ###
            #factor = 1
            #dist_med = np.median(distances)
            #weights = np.ceil((dist_med/np.mean(distances, axis=1)) * factor)
            #mod_wls = sm.WLS(matched_levels, d, weights=weights)
            #res = mod_wls.fit()
            ##print(res.params)
            #m = res.params
            ### TEST Weighted ICP ###

            # Store new tranformation matrix and offset vector
            self.matrix = m[0:-1, :]
            self.offset = m[-1, :]

            # Compare step by step delta
            d_compare = np.sum(np.square(self.matrix - matrix_old))
            d_compare = d_compare + np.sum(np.square(self.offset - offset_old))
            n_compare = np.sum(np.square(self.matrix)) + np.sum(np.square(self.offset))
            delta = sqrt(d_compare / n_compare)
            print("Delta: ", delta)

    def _set_matrix(self, data, target):
        """Set Matrix
        Set initial guess matrix"""
        matrix = self.matrix_create(self.matrix_func, target, data)
        return matrix

    def _set_offset(self, data, target):
        naxes = len(data[0, :])
        offset = np.ones(naxes)
        for n in xrange(naxes):
            offset[n] = np.min(target[:, n]) - np.min(data[:, n])
        return offset

