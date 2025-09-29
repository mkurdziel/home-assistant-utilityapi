from homeassistant.const import Platform

DOMAIN = "utilityapi"

CONF_API_KEY = "api_key"
CONF_LOOKBACK_DAYS = "lookback_days"

PLATFORMS = [Platform.SENSOR]

DEFAULT_BASE_URL = "https://utilityapi.com/api/v2"
DEFAULT_LOOKBACK_DAYS = 30
