"""
Settings utilities for Django apps.
"""

import re

from django.utils.module_loading import import_string
from django.core.exceptions import ImproperlyConfigured


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
        # Settings should be accessed as instance attributes
        if not instance:
            raise TypeError('Settings cannot be accessed as class attributes')
        try:
            return instance.user_settings[self.name]
        except KeyError:
            return self._get_default(instance)

    def _get_default(self, instance):
        # This is provided as a separate method for easier overriding
        if self.default is self.NO_DEFAULT:
            raise ImproperlyConfigured('Required setting: {}.{}'.format(instance.name, self.name))
        return self.default(instance) if callable(self.default) else self.default

    def __set__(self, instance, value):
        # This method exists so that the descriptor is considered a data-descriptor
        raise AttributeError('Settings are read-only')


class ImportStringSetting(Setting):
    """
    Property descriptor for a setting that is a dotted-path string that should be
    imported.
    """
    def __get__(self, instance, owner):
        return import_string(super().__get__(instance, owner))


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
    """
    MISSING_ARG_REGEX = r"missing \d+ required positional arguments?: "
    INVALID_ARG_MATCH = "got an unexpected keyword argument"
    ARG_NAME_REGEX = r"'(\w+)'"

    def __get__(self, instance, owner):
        factory_definition = super().__get__(instance, owner)
        factory = import_string(factory_definition['FACTORY'])
        kwargs = { k.lower(): v for k, v in factory_definition['PARAMS'].items() }
        # We want to convert type errors for missing or invalid arguments into
        # errors about missing or invalid settings
        try:
            return factory(**kwargs)
        except TypeError as exc:
            message = str(exc)
            if re.search(self.MISSING_ARG_REGEX, message):
                required = [
                    '{}.{}.PARAMS.{}'.format(instance.name, self.name, name.upper())
                    for name in re.findall(self.ARG_NAME_REGEX, message)
                ]
                raise ImproperlyConfigured(
                    'Required setting(s): {}'.format(', '.join(required))
                )
            elif self.INVALID_ARG_MATCH in message:
                match = re.search(self.ARG_NAME_REGEX, message)
                raise ImproperlyConfigured(
                    'Invalid setting: {}.{}.PARAMS.{}'.format(
                        instance.name, self.name, match.group(1).upper()
                    )
                )
            else:
                # Re-raise any other type error
                raise
