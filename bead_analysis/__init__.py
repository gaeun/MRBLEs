"""
Bead Analysis Package
=====================

This package contains the necessary classes, methods and data structures to perform the Bead Analysis for MRBLs.
"""

# !/usr/bin/env python

# [Future imports]
# Function compatibility between Python 2.x and 3.x
from __future__ import print_function, division
import sys
if sys.version_info < (3, 0):
    from future.standard_library import install_aliases
    from __builtin__ import *
    install_aliases()

# [File header]     | Copy and edit for each file in this project!
# title             : MRBLEs Analysis Package
# description       : Bead Analysis
# author            : Bjorn Harink
# credits           : Kurt Thorn, Huy Nguyen
# date              : 20160308
# version update    : 20171022
# version           : 0.6.0
# usage             : As module
# notes             : Do not quick fix functions for specific needs, keep them general!
# python_version    : >2.7 and >3.6

# [Module Imports]
from bead_analysis.core import *
from bead_analysis.data import *
import bead_analysis.simp
import bead_analysis.inspect
import bead_analysis.kinetics

# [Main header with project metadata] | Only in the main file!
# Name of package
__name__        = "bead_analysis"
__package__     = "bead_analysis"
# Copyright and credits
__copyright__   = ("Copyright 2017 - "
                   "The Encoded Beads Project - "
                   "ThornLab@UCSF and "
                   "FordyceLab@Stanford")
# Original author(s) of this Python project, like: ("...", 
__author__      = ("Bjorn Harink")  #               "name")
# People who contributed to this Python project, like: ["...",
__credits__     = ["Kurt Thorn",  #                     "name"]
                   "Huy Nguyen"]
# Maintainer contact information
__maintainer__  = "Bjorn Harink" 
__email__       = "bjorn@harink.info"
# Software information
__license__     = "MIT" 
__version__     = "v0.6.0"
__status__      = "Development"
# Package settings
__all__         = ['core', 'data']

__bibtex__ = r"""@Article{Harink:2017,
  Author    = {Harink, Bjorn},
  Title     = {MRBLEs Analysis},
  Journal   = {SoftwareX},
  Volume    = {x},
  Number    = {x},
  Pages     = {xx--xx},
  abstract  = {MRBLEs analysis sofwtare is...},
  publisher = {Elsevier},
  year      = 2017
}"""

print(__copyright__)
