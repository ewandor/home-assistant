"""
Adds support for advanced thermostat units.


"""
import logging

import voluptuous as vol
from collections import OrderedDict

from homeassistant.components import switch
from homeassistant.components.climate import (
    STATE_HEAT, STATE_COOL, STATE_IDLE, ClimateDevice, PLATFORM_SCHEMA)
from homeassistant.components.climate.generic_thermostat import GenericThermostat
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT, STATE_ON, STATE_OFF, ATTR_TEMPERATURE)
from homeassistant.helpers import condition
from homeassistant.helpers.event import track_state_change
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['switch', 'sensor']

DEFAULT_TOLERANCE = 0.3
DEFAULT_NAME = 'Advanced Thermostat'

DEFAULT_OPERATION_NAME = 'default'

CONF_NAME = 'name'
CONF_HEATER = 'heater'
CONF_SENSOR = 'target_sensor'
CONF_MIN_TEMP = 'min_temp'
CONF_MAX_TEMP = 'max_temp'
CONF_TARGET_TEMP = 'target_temp'
CONF_AC_MODE = 'ac_mode'
CONF_MIN_DUR = 'min_cycle_duration'
CONF_TOLERANCE = 'tolerance'
CONF_OPERATION_LIST = 'operation_list'
CONF_ICON = 'icon'

MODE_SCHEMA = vol.Schema({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_SENSOR): cv.entity_id,
    vol.Optional(CONF_ICON): cv.string,
    vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HEATER): cv.entity_id,
    vol.Required(CONF_SENSOR): cv.entity_id,
    vol.Optional(CONF_AC_MODE): cv.boolean,
    vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
    vol.Optional(CONF_MIN_DUR): vol.All(cv.time_period, cv.positive_timedelta),
    vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
    vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
    vol.Optional(CONF_OPERATION_LIST, default=[{CONF_NAME: DEFAULT_OPERATION_NAME}]):
        vol.All(cv.ensure_list, [MODE_SCHEMA]),
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the advanced thermostat."""
    name = config.get(CONF_NAME)
    heater_entity_id = config.get(CONF_HEATER)
    sensor_entity_id = config.get(CONF_SENSOR)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    ac_mode = config.get(CONF_AC_MODE)
    min_cycle_duration = config.get(CONF_MIN_DUR)
    tolerance = config.get(CONF_TOLERANCE)
    operation_list = config.get(CONF_OPERATION_LIST)

    add_devices([AdvancedThermostat(
        hass, name, heater_entity_id, sensor_entity_id, min_temp, max_temp,
        target_temp, ac_mode, min_cycle_duration, tolerance, operation_list)])


class AdvancedThermostat(GenericThermostat):
    """Representation of a AdvancedThermostat device."""

    def __init__(self, hass, name, heater_entity_id, sensor_entity_id,
                 min_temp, max_temp, target_temp, ac_mode, min_cycle_duration,
                 tolerance, operation_list):
        """Initialize the thermostat."""
        self.hass = hass
        self._name = name

        self.heater_entity_id = heater_entity_id
        self.ac_mode = ac_mode
        self.min_cycle_duration = min_cycle_duration
        self._tolerance = tolerance

        self._active = False
        self._cur_temp = None
        self._min_temp = min_temp
        self._max_temp = max_temp

        self._default_sensor_entity_id = sensor_entity_id
        self._default_target_temp = target_temp

        self._sensor_callback = None

        self.current_operation_mode = None
        self.default_operation_mode = None
        self.operation_dict = OrderedDict()
        for i, operation in enumerate(operation_list):
            name = operation[CONF_NAME] if CONF_NAME in operation else i
            if i == 0:
                self.default_operation_mode = name

            self.operation_dict[name] = OperationMode(
                operation[CONF_SENSOR] if CONF_SENSOR in operation else sensor_entity_id,
                operation[CONF_TARGET_TEMP] if CONF_TARGET_TEMP in operation else target_temp,
            )

        self._unit = hass.config.units.temperature_unit
        self._set_current_operation_mode(self.default_operation_mode)

    def set_mode(self, **kwargs):
        pass

    def set_operation_mode(self, operation_mode):
        self._set_current_operation_mode(operation_mode)
        self.schedule_update_ha_state()

    def _set_current_operation_mode(self, operation_mode):
        self.current_operation_mode = operation_mode
        operation = self.operation_dict[operation_mode]

        self._target_temp = operation.target_temp
        self._set_target_sensor(operation.target_sensor)

        sensor_state = self.hass.states.get(operation.target_sensor)
        if sensor_state:
            self._update_temp(sensor_state)
            self._control_heating()

    def _set_target_sensor(self, target_sensor):
        if self._sensor_callback is not None:
            self._sensor_callback()

        self._sensor_callback = async_track_state_change(self.hass, target_sensor, self._async_sensor_changed)

    @property
    def current_operation(self):
        return self.operation_mode

    @property
    def operation_list(self):
        """Return the operation modes list."""
        return list(self.operation_dict.keys())

    @property
    def operation_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self.current_operation_mode


class OperationMode:
    def __init__(self, target_sensor, target_temp):
        self.target_sensor = target_sensor
        self.target_temp = target_temp
