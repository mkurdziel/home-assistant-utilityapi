from homeassistant.const import Platform

DOMAIN = "utilityapi"

CONF_API_KEY = "api_key"

PLATFORMS = [Platform.SENSOR]

DEFAULT_BASE_URL = "https://utilityapi.com/api/v2"
