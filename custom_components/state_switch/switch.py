"""Support for switches which integrates with other components."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
import logging

from homeassistant.components.switch import (
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA,
    SwitchEntity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    CONF_SWITCHES,
    CONF_UNIQUE_ID,
    CONF_VALUE_TEMPLATE,
    STATE_OFF,
    STATE_ON,
)
from threading import Timer
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.script import Script
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from homeassistant.components.template.const import DOMAIN
from homeassistant.components.template.template_entity import (
    TEMPLATE_ENTITY_COMMON_SCHEMA_LEGACY,
    TemplateEntity,
    rewrite_common_legacy_to_modern_conf,
)

from homeassistant.components.template.switch import SwitchTemplate, CONF_TURN_ON, CONF_TURN_OFF

ON_OFF_DELAY = "on_off_delay"

_LOGGER = logging.getLogger(__name__)

SWITCH_SCHEMA = vol.All(
    cv.deprecated(ATTR_ENTITY_ID),
    vol.Schema(
        {
            vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
            vol.Required(CONF_TURN_ON): cv.SCRIPT_SCHEMA,
            vol.Required(CONF_TURN_OFF): cv.SCRIPT_SCHEMA,
            vol.Required(ON_OFF_DELAY): int,
            vol.Optional(ATTR_FRIENDLY_NAME): cv.string,
            vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
            vol.Optional(CONF_UNIQUE_ID): cv.string,
        }
    ).extend(TEMPLATE_ENTITY_COMMON_SCHEMA_LEGACY.schema),
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_SWITCHES): cv.schema_with_slug_keys(SWITCH_SCHEMA)}
)


async def _async_create_entities(hass, config):
    """Create the Template switches."""
    switches = []

    for object_id, entity_config in config[CONF_SWITCHES].items():
        entity_config = rewrite_common_legacy_to_modern_conf(hass, entity_config)
        unique_id = entity_config.get(CONF_UNIQUE_ID)

        switches.append(
            StateSwitch(
                hass,
                object_id,
                entity_config,
                unique_id,
            )
        )

    return switches


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the template switches."""
    async_add_entities(await _async_create_entities(hass, config))


class StateSwitch(SwitchTemplate):
    """Representation of a Template switch."""

    def __init__(
        self,
        hass,
        object_id,
        config,
        unique_id,
    ):
        """Initialize the Template switch."""
        super().__init__(
            hass, object_id, config, unique_id
        )

        self._on_off_delay = config[ON_OFF_DELAY]
        self._reset_timer = None
        self._old_state = False

    @callback
    def _update_state(self, result):
        self.timer_reset()
        super()._update_state(result)
        if isinstance(result, TemplateError):
            self._state = None
            return

        if isinstance(result, bool):
            self._state = result
            return

        if isinstance(result, str):
            self._state = result.lower() in ("true", STATE_ON)
            return

        self._state = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Fire the on action."""
        self.timer_reset()
        self._reset_timer = Timer(self._on_off_delay/1000, self.reset)
        self._reset_timer.start()
        await self.async_run_script(self._on_script, context=self._context)
        self._old_state = False
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Fire the off action."""
        self.timer_reset()
        self._reset_timer = Timer(self._on_off_delay/1000, self.reset)
        self._reset_timer.start()
        await self.async_run_script(self._off_script, context=self._context)
        self._old_state = True
        self._state = False
        self.async_write_ha_state()

    def reset(self) -> None:
        self.timer_reset()
        self._state = self._old_state
        self.async_write_ha_state()

    def timer_reset(self):
        if self._reset_timer != None:
            self._reset_timer.cancel()
            self._reset_timer = None
