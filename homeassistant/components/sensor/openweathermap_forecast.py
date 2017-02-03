"""
Support for the OpenWeatherMap (OWM) service.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.openweathermap/
"""
import logging
from datetime import datetime, date, time, timedelta

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_API_KEY, CONF_NAME, TEMP_CELSIUS, TEMP_FAHRENHEIT,
    CONF_MONITORED_CONDITIONS, ATTR_ATTRIBUTION)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import homeassistant.util.dt as dt_util

REQUIREMENTS = ['pyowm==2.6.1']

_LOGGER = logging.getLogger(__name__)

CONF_ATTRIBUTION = "Data provided by OpenWeatherMap"
CONF_FORECAST = 'forecast'

DEFAULT_NAME = 'OWM'

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=120)

SENSOR_TYPES = {
    'forecast_weather': ['Forecast Condition', None],
    'forecast_temperature': ['Forecast Temperature', None]
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=[]):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_FORECAST, default=False): cv.boolean
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the OpenWeatherMap sensor."""
    if None in (hass.config.latitude, hass.config.longitude):
        _LOGGER.error("Latitude or longitude not set in Home Assistant config")
        return False

    from pyowm import OWM

    SENSOR_TYPES['forecast_temperature'][1] = hass.config.units.temperature_unit

    name = config.get(CONF_NAME)

    owm = OWM(config.get(CONF_API_KEY))

    if not owm:
        _LOGGER.error("Unable to connect to OpenWeatherMap")
        return False

    data = WeatherData(owm, hass.config.latitude, hass.config.longitude)

    dev = []
    for i in range(0, 7):
        dev.append(OpenWeatherMapSensor(
            name, data, 'forecast_weather', None, i))
        dev.append(OpenWeatherMapSensor(
            name, data, 'forecast_temperature', SENSOR_TYPES['forecast_temperature'][1], i))

    for day_offset in range(1, 4):
        dev.append(OpenWeatherMapSensor(
            name, data, 'forecast_weather', None, None, day_offset))
        dev.append(OpenWeatherMapSensor(
            name, data, 'forecast_temperature', SENSOR_TYPES['forecast_temperature'][1], None, day_offset))

    add_devices(dev)


class OpenWeatherMapSensor(Entity):
    """Implementation of an OpenWeatherMap sensor."""

    def __init__(self, name, weather_data, sensor_type, temp_unit, index, day_offset = None):
        if day_offset is None:
            name_suffix = "%dh" % ((index + 1) * 3)
        else:
            name_suffix = "%dd" % day_offset

        """Initialize the sensor."""
        self.client_name = name
        self._name = SENSOR_TYPES[sensor_type][0] + "_" + name_suffix
        self.owa_client = weather_data
        self.temp_unit = temp_unit
        self.type = sensor_type
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

        self._cast_index = index
        self._day_offset = day_offset

        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{} {}'.format(self.client_name, self._name)

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
        }

    def update(self):
        """Get the latest data from OWM and updates the states."""
        self.owa_client.update()
        fc_data = self.owa_client.fc_data

        followed_cast = None
        if self._day_offset is None:
            followed_cast = fc_data.get_weathers()[self._cast_index]
        else:
            target_date = datetime.combine(date.today() + timedelta(self._day_offset), time(hour=15, tzinfo=dt_util.UTC))
            for cast in fc_data.get_weathers():
                if cast.get_reference_time('date') == target_date:
                    followed_cast = cast
                    break

        if self.type == 'forecast_weather':
            self._state = followed_cast.get_status()
        elif self.type == 'forecast_temperature':
            if self.temp_unit == TEMP_CELSIUS:
                self._state = round(followed_cast.get_temperature('celsius')['temp'], 1)
            elif self.temp_unit == TEMP_FAHRENHEIT:
                self._state = round(followed_cast.get_temperature('fahrenheit')['temp'],
                                    1)
            else:
                self._state = round(followed_cast.get_temperature()['temp'], 1)


class WeatherData(object):
    """Get the latest data from OpenWeatherMap."""

    def __init__(self, owm, latitude, longitude):
        """Initialize the data object."""
        self.owm = owm
        self.latitude = latitude
        self.longitude = longitude
        self.fc_data = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get the latest data from OpenWeatherMap."""
        obs = self.owm.three_hours_forecast_at_coords(
            self.latitude, self.longitude)
        self.fc_data = obs.get_forecast()
