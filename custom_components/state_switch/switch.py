"""Support for switches which integrates with other components."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
import logging

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    CONF_SWITCHES,
    CONF_UNIQUE_ID,
    CONF_VALUE_TEMPLATE,
    STATE_ON,
    CONF_STATE,
)
from threading import Timer
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from homeassistant.components.template.template_entity import (
    LEGACY_FIELDS as TEMPLATE_ENTITY_LEGACY_FIELDS,
    TEMPLATE_ENTITY_COMMON_SCHEMA_LEGACY,
    rewrite_common_legacy_to_modern_conf,
)

from homeassistant.components.template.switch import (
    SwitchTemplate,
    CONF_TURN_ON, CONF_TURN_OFF,
    SWITCH_PLATFORM_SCHEMA,
    rewrite_options_to_modern_conf,
    rewrite_common_legacy_to_modern_conf,
)

ON_OFF_DELAY = "on_off_delay"

_LOGGER = logging.getLogger(__name__)

LEGACY_FIELDS = TEMPLATE_ENTITY_LEGACY_FIELDS | {
    CONF_VALUE_TEMPLATE: CONF_STATE,
}

DEFAULT_NAME = "Template Switch"

LEGACY_SWITCH_SCHEMA = vol.All(
    cv.deprecated(ATTR_ENTITY_ID),
    vol.Schema(
        {
            vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
            vol.Required(CONF_TURN_ON): cv.SCRIPT_SCHEMA,
            vol.Required(CONF_TURN_OFF): cv.SCRIPT_SCHEMA,
            vol.Optional(ATTR_FRIENDLY_NAME): cv.string,
            vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
            vol.Optional(CONF_UNIQUE_ID): cv.string,
            vol.Optional(ON_OFF_DELAY): int
        }
    ).extend(TEMPLATE_ENTITY_COMMON_SCHEMA_LEGACY.schema),
)

PLATFORM_SCHEMA = SWITCH_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_SWITCHES): cv.schema_with_slug_keys(LEGACY_SWITCH_SCHEMA),
    }
)
async def _async_create_entities(hass, config):
    """Create the Template switches."""
    switches = []

    for object_id, entity_config in config[CONF_SWITCHES].items():
        entity_config = rewrite_common_legacy_to_modern_conf(hass, entity_config)
        entity_config = rewrite_options_to_modern_conf(entity_config)
        unique_id = entity_config.get(CONF_UNIQUE_ID)

        switches.append(
            StateSwitch(
                hass,
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
        config,
        unique_id,
    ):
        """Initialize the Template switch."""
        super().__init__(
            hass, config, unique_id
        )

        self._on_off_delay = config.get(ON_OFF_DELAY, 0)
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
        if on_script := self._action_scripts.get(CONF_TURN_ON):
            await self.async_run_script(on_script, context=self._context)
        self._old_state = False
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Fire the off action."""
        self.timer_reset()
        self._reset_timer = Timer(self._on_off_delay/1000, self.reset)
        self._reset_timer.start()
        if off_script := self._action_scripts.get(CONF_TURN_OFF):
            await self.async_run_script(off_script, context=self._context)
        self._old_state = True
        self._state = False
        self.async_write_ha_state()

    def reset(self) -> None:
        self.timer_reset()
        self._state = self._old_state
        self.schedule_update_ha_state()

    def timer_reset(self):
        if self._reset_timer != None:
            self._reset_timer.cancel()
            self._reset_timer = None
