"""
VLC Remote platform.

For more details about his platform, please refer to the documentation at
https://github.com/colemamd/vlc-remote

VLC REST API: https://wiki.videolan.org/VLC_HTTP_requests/
"""
import asyncio
import logging
import requests

import aiohttp
import voluptuous as vol
import xmltodict

from homeassistant.components.media_player import PLATFORM_SCHEMA, MediaPlayerDevice
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_MUSIC,
    MEDIA_TYPE_VIDEO,
    MEDIA_TYPE_PLAYLIST,
    SUPPORT_CLEAR_PLAYLIST,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PAUSE,
    SUPPORT_PLAY,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SEEK,
    SUPPORT_STOP,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)

from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_PASSWORD,
    CONF_USERNAME,
    STATE_IDLE,
    STATE_OFF,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNKNOWN,
)

from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)


DEFAULT_NAME = "VLC Remote"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = "8080"
DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""

DATA_VLCREMOTE = "vlc remote"

TIMEOUT = 10

SUPPORT_VLCREMOTE = (
    SUPPORT_PAUSE
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_PLAY
    | SUPPORT_VOLUME_SET
    | SUPPORT_STOP
    | SUPPORT_VOLUME_STEP
    | SUPPORT_PREVIOUS_TRACK
    | SUPPORT_NEXT_TRACK
    | SUPPORT_SEEK
    | SUPPORT_CLEAR_PLAYLIST
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up a VLC Remote."""
    if DATA_VLCREMOTE not in hass.data:
        hass.data[DATA_VLCREMOTE] = dict()

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    entity = VlcServer(name, host, port, username, password, hass)

    hass.data[DATA_VLCREMOTE] = entity
    async_add_entities([entity])


class VlcServer(MediaPlayerDevice):
    """Representation of a VLC server."""

    def __init__(self, name, host, port, username, password, hass):
        """Initialize the VLC device."""
        self._name = name
        self._port = port
        self._host = host
        self._username = username
        self._password = password
        self._volume = None
        self._muted = None
        self._state = {}
        self._media_position = None
        self._media_duration = None
        self._media_metadata = {}
        self._currentplaylist = None

    async def fetch_data(self, command=None, value=None):
        """VLC HTTP interface."""
        url_stem = "http://{}:{}/requests/status.xml"
        if command is None:
            url = url_stem.format(self._host, self._port)
        else:
            url_stem = url_stem + "?command={}"
            url = url_stem.format(self._host, self._port, command)

        _LOGGER.debug("URL: %s", url)

        try:
            req = requests.get(url, auth=(self._username, self._password))

            if req.status_code != 200:
                _LOGGER.error(
                    "Query failed, response code: %s Full message: %s", req.status, req
                )
                return {}

            data = xmltodict.parse(req.text, process_namespaces=True).get("root")

        except Exception as error:
            _LOGGER.error("Failed communicating with VLC Server: %s", error)
            return {}

        try:
            return data

        except AttributeError:
            _LOGGER.error("Received invalid response: %s", data)
            return {}

    async def update(self):
        """Get the latest details from the device."""
        status = await self.fetch_data()
        self._status = status

        if "information" in self._status:
            try:
                for info in self._status["information"]["category"]:
                    if info.get("@name") == "meta":
                        self._media_metadata = info["info"]
            except:
                pass

        if status.get("state") == "playing":
            self._state = STATE_PLAYING
        elif status.get("state") == "paused":
            self._state = STATE_PAUSED
        elif status.get("state") == "stopped":
            self._state = STATE_IDLE

        self._media_position = int(status.get("position"))
        self._media_duration = int(status.get("length"))

        self._volume = int(status.get("volume")) / 256
        self._muted = int(status.get("volume")) == 0

        return True

    @property
    def name(self):
        """Return name of the device."""
        return self._name

    @property
    def state(self):
        """Return state of the device."""
        return self._state

    @property
    def media_title(self):
        """Title of currently playing media."""
        return self._state.get("title", None)

    @property
    def media_artist(self):
        """Artist of currently playing media."""
        return self._state.get("artist", None)

    @property
    def media_type(self):
        """Type of media being played."""
        return self._state.get("Type", None)

    @property
    def volume_level(self):
        """Volume level of the media player (0...1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_VLCREMOTE

    @property
    def media_duration(self):
        """Duration of currently playing media in seconds."""
        return self._media_duration

    @property
    def media_position(self):
        """Position of currently playing media in seconds."""
        return self._media_position

    def media_play(self):
        """Send play command."""
        self.fetch_data(command="pl_play")
        self._state = STATE_PLAYING

    def media_pause(self):
        """Send pause command."""
        self.fetch_data(command="pl_pause")
        self._state = STATE_PAUSED

    def media_stop(self):
        """Send stop command."""
        self.fetch_data(command="pl_stop")
        self._state = STATE_IDLE
