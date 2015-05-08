sedml2py
========

SED-ML to Python converter

Sedml2py converts SED-ML files to executable Python scripts. The Python scripts can be executed in Tellurium/RoadRunner environment. To use, simply type:

"""
sedml_to_python(Path_to_SEDML_file)
"""

Currently, three different simulation types are supported: UniformTimeCourse, OneStep, and SteadyState. All the output is fully supported as well (Plot2D, Plot3D, Report).

This file is necessary to use Import Plugins.