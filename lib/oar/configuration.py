# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import, unicode_literals

import errno
import pprint

from io import open

from .compat import iteritems, integer_types


class Configuration(dict):
    """Works exactly like a dict but provides ways to fill it from files.

    :param defaults: an optional dictionary of default values
    """
    DEFAULT_CONFIG_FILES = ["/etc/oar/oar.conf"]

    DEFAULT_CONFIG = {
        'SQLALCHEMY_NATIVE_UNICODE': True,
        'SQLALCHEMY_ECHO': False,
        'SQLALCHEMY_POOL_SIZE': None,
        'SQLALCHEMY_POOL_TIMEOUT': None,
        'SQLALCHEMY_POOL_RECYCLE': None,
        'SQLALCHEMY_MAX_OVERFLOW': None,
        'LOG_LEVEL': 1,
        'LOG_FORMAT': '[%(levelname)s] [%(asctime)s] [%(name)s]: %(message)s'
    }

    def __init__(self, defaults=None):
        defaults = dict(self.DEFAULT_CONFIG)
        defaults.update(defaults or {})
        dict.__init__(self, defaults)
        for config_file in self.DEFAULT_CONFIG_FILES:
            self.load_file(config_file, silent=True)

    def load_file(self, filename, comment_char="#", strip_quotes=True,
                  silent=False):
        """Updates the values in the config from a config file.
        :param filename: the filename of the config.  This can either be an
                         absolute filename or a filename relative to the
                         root path.
        :param comment_char: The string character used to comment
        :param strip_quotes: Strip the quotes
        """
        decimal_types = integer_types + (float, )
        try:
            equal_char = "="
            with open(filename, encoding="utf-8") as config_file:
                for line in config_file:
                    if comment_char in line:
                        line, comment = line.split(comment_char, 1)
                    if equal_char in line:
                        key, value = line.split(equal_char, 1)
                        key = key.strip()
                        value = value.strip()
                        value = value.strip('"\'')
                        value = self._try_convert_value(value, decimal_types)
                        self[key] = value
        except IOError as e:
            if silent and e.errno in (errno.ENOENT, errno.EISDIR):
                return False
            e.strerror = 'Unable to load configuration file (%s)' % e.strerror
            raise
        return True

    def _try_convert_value(self, value, decimal_types):
        if value.isdecimal():
            for _type in decimal_types:
                try:
                    return _type(value)
                except:
                    pass
        return value

    def get_namespace(self, namespace, lowercase=True, trim_namespace=True):
        """Returns a dictionary containing a subset of configuration options
        that match the specified namespace/prefix. Example usage::

            config['OARSUB_DEFAULT_RESOURCES'] = 2
            config['OARSUB_FORCE_JOB_KEY'] = '/resource_id=1'
            config['OARSUB_NODES_RESOURCES'] = 'network_address'
            oarsub_config = config.get_namespace('OARSUB_')

        The resulting dictionary `oarsub_config` would look like::

            {
                'default_resources': 2,
                'force_job_key': '/resource_id=1',
                'nodes_resources': 'network_address'
            }

        This is often useful when configuration options map directly to keyword
        arguments in functions or class constructors.

        :param namespace: a configuration namespace
        :param lowercase: a flag indicating if the keys of the resulting
        dictionary should be lowercase
        :param trim_namespace: a flag indicating if the keys of the resulting
        dictionary should not include the namespace
        """
        rv = {}
        for k, v in iteritems(self):
            if not k.startswith(namespace):
                continue
            if trim_namespace:
                key = k[len(namespace):]
            else:
                key = k
            if lowercase:
                key = key.lower()
            rv[key] = v
        return rv

    def __str__(self):
        return pprint.pprint(self)