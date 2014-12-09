# -*- coding: utf-8 -*-
"""
    oar-lib
    ~~~~~~~

    Python version of OAR Common Library

"""
from types import ModuleType
import sys

from oar.compat import iteritems

__version__ = '0.1-dev'

# The implementation of a lazy-loading module in this file replaces the
# oar package when imported from within.  Attribute access to the oar
# module will then lazily import from the modules that implement the objects.


# import mapping to objects in other modules
all_by_module = {
    'oar.models': ['Accounting', 'AdmissionRule', 'AssignedResource',
                   'Challenge', 'EventLog', 'EventLogHostname', 'File',
                   'FragJob', 'GanttJobsPrediction', 'GanttJobsPredictionsLog',
                   'GanttJobsPredictionsVisu', 'GanttJobsResource',
                   'GanttJobsResourcesLog', 'GanttJobsResourcesVisu', 'Job',
                   'JobDependencie', 'JobResourceDescription',
                   'JobResourceGroup', 'JobStateLog', 'JobType',
                   'MoldableJobDescription', 'Queue', 'Resource',
                   'ResourceLog', 'Scheduler'],
    'oar.exceptions': ['OARException', 'InvalidConfiguration',
                       'DatabaseError', 'DoesNotExist'],
    'oar.database': ['Database'],
    'oar.logging': ['create_logger', 'get_logger'],
    'oar.configuration': ['Configuration'],
    'oar.utils': [],
    'oar.globals': ['config', 'db', 'logger'],
}

# modules that should be imported when accessed as attributes of oar
attribute_modules = frozenset(['configuration', 'database', 'exceptions',
                               'logging', 'models', 'utils'])


object_origins = {}
for module, items in iteritems(all_by_module):
    for item in items:
        object_origins[item] = module


class module(ModuleType):
    """Automatically import objects from the modules."""

    def __getattr__(self, name):
        if name in object_origins:
            module = __import__(object_origins[name], None, None, [name])
            for extra_name in all_by_module[module.__name__]:
                setattr(self, extra_name, getattr(module, extra_name))
            return getattr(module, name)
        elif name in attribute_modules:
            __import__('oar.' + name)
        return ModuleType.__getattribute__(self, name)

    def __dir__(self):
        """Just show what we want to show."""
        result = list(new_module.__all__)
        result.extend(('__file__', '__path__', '__doc__', '__all__',
                       '__docformat__', '__name__', '__path__',
                       '__package__', '__version__'))
        return result

# keep a reference to this module so that it's not garbage collected
old_module = sys.modules['oar']


# setup the new module and patch it into the dict of loaded modules
new_module = sys.modules['oar'] = module('oar')
new_module.__dict__.update({
    '__file__':         __file__,
    '__package__':      'oar',
    '__path__':         __path__,
    '__doc__':          __doc__,
    '__version__':      __version__,
    '__all__':          tuple(object_origins) + tuple(attribute_modules),
    '__docformat__':    'restructuredtext en'
})
