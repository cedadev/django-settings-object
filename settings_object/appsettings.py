# -*- coding: utf-8 -*-
"""
Settings utilities for Django apps.
"""

import re
from functools import reduce
from importlib import import_module

try:
    from django.core.exceptions import ImproperlyConfigured
except ImportError:
    class ImproperlyConfigured(RuntimeError):
        pass


def import_callable(python_path):
    """
    Smarter version of Django's import_string that can deal with importing
    nested classes and static method references.
    """
    module_parts = python_path.split('.')
    attribute_parts = []
    imported_mod = None
    # Keep removing parts from the path until we find a module
    while imported_mod is None and module_parts:
        try:
            imported_mod = import_module('.'.join(module_parts))
        except ModuleNotFoundError:
            attribute_parts.insert(0, module_parts.pop())
    # If no module was found, raise a module not found error for the original path
    if imported_mod is None:
        _ = import_module(python_path)
    # Otherwise, use getattr to traverse the attribute parts
    return reduce(getattr, attribute_parts, imported_mod)


class SettingsObject:
    """
    Object representing a collection of settings.

    Args:
        name: The name of the settings object.
        user_settings: A dictionary of user settings. OPTIONAL. If not given,
                       use ``django.conf.settings.<name>``.
    """
    def __init__(self, name, user_settings = None):
        self.name = name
        if user_settings is None:
            from django.conf import settings
            user_settings = getattr(settings, self.name, {})
        self.user_settings = user_settings


class Setting:
    """
    Property descriptor for a setting.

    Args:
        default: Provides a default for the setting. If a callable is given, it
                 is called with the owning py:class:`SettingsObject` as it's only
                 argument. Defaults to ``NO_DEFAULT``.
    """
    #: Sentinel object representing no default. A sentinel is required because
    #: ``None`` is a valid default value.
    NO_DEFAULT = object()

    def __init__(self, default = NO_DEFAULT):
        self.default = default

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        # Settings should be accessed as instance attributes
        if not instance:
            raise TypeError('Settings cannot be accessed as class attributes')
        try:
            return instance.user_settings[self.name]
        except KeyError:
            return self._get_default(instance)

    def _get_default(self, instance):
        # This is provided as a separate method for easier overriding
        if self.default is self.NO_DEFAULT:
            raise ImproperlyConfigured('Required setting: {}.{}'.format(instance.name, self.name))
        elif callable(self.default):
            try:
                return self.default(instance)
            except TypeError:
                return self.default()
        else:
            return self.default

    def __set__(self, instance, value):
        # This method exists so that the descriptor is considered a data-descriptor
        raise AttributeError('Settings are read-only')


class MergedDictSetting(Setting):
    """
    Property descriptor for a setting that comprises of a dictionary of defaults
    that is merged with the user-provided value.
    """
    def __init__(self, defaults):
        self.defaults = defaults
        super().__init__(default = dict)

    def __get__(self, instance, owner):
        merged = self.defaults.copy()
        merged.update(super().__get__(instance, owner))
        return merged


class NestedSetting(Setting):
    """
    Property descriptor for a setting whose value is a nested settings object.
    """
    def __init__(self, settings_class):
        self.settings_class = settings_class
        super().__init__(default = dict)

    def __get__(self, instance, owner):
        # Use the value of the setting as user values for an instance of the
        # nested settings class, and return that
        return self.settings_class(
            '{}.{}'.format(instance.name, self.name),
            super().__get__(instance, owner)
        )


class ImportStringSetting(Setting):
    """
    Property descriptor for a setting that is a dotted-path string that should be
    imported.
    """
    def __get__(self, instance, owner):
        return import_callable(
            super(ImportStringSetting, self).__get__(instance, owner)
        )


class ObjectFactorySetting(Setting):
    """
    Property descriptor for an 'object factory' setting of the form::

        {
            'FACTORY': 'dotted.path.to.factory.function',
            'PARAMS': {
                'PARAM1': 'value for param 1',
            },
        }

    The ``FACTORY`` can either be a constructor or a dedicated factory function.

    Keys in ``PARAMS`` are lower-cased and used as ``kwargs`` for the factory.

    Object factory settings can be nested, so that a parameter of an object factory
    can be another object factory.
    """
    MISSING_ARG_REGEX = r"missing \d+ required positional arguments?: "
    INVALID_ARG_MATCH = "got an unexpected keyword argument"
    ARG_NAME_REGEX = r"'(\w+)'"

    def _process_item(self, item, prefix):
        # If the item is a factory dict, do some processing
        if isinstance(item, dict) and 'FACTORY' in item:
            factory = import_callable(item['FACTORY'])
            # Process the params for nested factory definitions
            kwargs = {
                k.lower(): self._process_item(v, '{}.PARAMS.{}'.format(prefix, k))
                for k, v in item.get('PARAMS', {}).items()
            }
            # We want to convert type errors for missing or invalid arguments into
            # errors about missing or invalid settings
            try:
                return factory(**kwargs)
            except TypeError as exc:
                message = str(exc)
                if re.search(self.MISSING_ARG_REGEX, message):
                    required = [
                        '{}.PARAMS.{}'.format(prefix, name.upper())
                        for name in re.findall(self.ARG_NAME_REGEX, message)
                    ]
                    raise ImproperlyConfigured(
                        'Required setting(s): {}'.format(', '.join(required))
                    )
                elif self.INVALID_ARG_MATCH in message:
                    match = re.search(self.ARG_NAME_REGEX, message)
                    raise ImproperlyConfigured(
                        'Invalid setting: {}.PARAMS.{}'.format(
                            prefix, match.group(1).upper()
                        )
                    )
                else:
                    # Re-raise any other type error
                    raise
        # For any other dict, convert the values if required
        if isinstance(item, dict):
            return {
                k: self._process_item(v, '{}.{}'.format(prefix, k))
                for k, v in item.items()
            }
        # For a list or tuple, convert the elements if required
        if isinstance(item, (list, tuple)):
            return [
                self._process_item(v, '{}[{}]'.format(prefix, i))
                for i, v in enumerate(item)
            ]
        # For anything else, just return the item
        return item

    def __get__(self, instance, owner):
        return self._process_item(
            super(ObjectFactorySetting, self).__get__(instance, owner),
            '{}.{}'.format(instance.name, self.name)
        )
