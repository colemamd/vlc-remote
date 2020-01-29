"""Control VLC on a remote system using HTTP API."""
import logging
import requests
import voluptuous as vol
import xmltodict

import homeassistant.helpers.config_validation as cv

from homeassistant.components.media_player import (
    SUPPORT_PAUSE,
    PLATFORM_SCHEMA,
    SUPPORT_SEEK,
    SUPPORT_VOLUME_SET,
    SUPPORT_PLAY,
    ATTR_MEDIA_ENQUEUE,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_STOP,
    MediaPlayerDevice,
)

from homeassistant.const import (
    STATE_OFF,
    STATE_PLAYING,
    STATE_PAUSED,
    STATE_UNKNOWN,
    STATE_IDLE,
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    CONF_USERNAME,
)

from homeassistant.helpers.aiohttp_client import async_get_clientsession

REQUIREMENTS = ["xmltodict==0.10.2"]

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "VLC Remote"
DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""
TIMEOUT = 10

SUPPORT_VLCREMOTE = (
    SUPPORT_PAUSE
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_PLAY
    | SUPPORT_VOLUME_SET
    | SUPPORT_STOP
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)


def setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up a VLC Remote."""
    async_add_devices(
        [
            VlcServer(
                config.get(CONF_NAME, DEFAULT_NAME),
                config.get(CONF_HOST),
                config.get(CONF_PORT),
                config.get(CONF_USERNAME, DEFAULT_USERNAME),
                config.get(CONF_PASSWORD, DEFAULT_PASSWORD),
            )
        ]
    )


class VlcServer(MediaPlayerDevice):
    """Representation of a VLC server."""

    def __init__(self, name, host, port, username, password):
        """Initialize the VLC device."""
        self._status = {}
        self._name = name
        self._port = port
        self._host = host
        self._username = username
        self._password = password
        self._volume = None
        self._muted = None
        self._state = None
        self._media_position = None
        self._media_duration = None
        self._media_metadata = {}

    def fetch_data(self, command=None, value=None):
        """VLC HTTP interface."""
        url_stem = "http://{}:{}/requests.status.xml"
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

    def update(self):
        """Get the latest details from the device."""
        status = self.fetch_data()
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
        else:
            self._state = STATE_IDLE

        self._media_position = int(status.get("time"))
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
        filename = "None"
        try:
            if self._media.metadata != {}:
                for item in self._media_metadata:
                    if item["@name"] == "title":
                        title = item["#text"]
                    if item["@name"] == "filename":
                        filename = item["#text"]
            return title
        except:
            return filename

    @property
    def media_artist(self):
        """Artist of currently playing media."""
        try:
            if self._media_metadata != {}:
                for item in self._media_metadata:
                    if item["@name"] == "showName":
                        artist = item["#text"]
            return artist
        except:
            return "None"

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

    def mute_volume(self, mute):
        """Mute the volume."""
        mute_numeric = "0" if mute else "256"
        self.fetch_data(command="volume&val={}".format(mute_numeric))
        self._muted = mute

    def set_volume_level(self, volume):
        """Set volume level, range 0...1."""
        new_volume = str(int(volume * 256))
        self.fetch_data(command="volume&val={}".format(new_volume))
        self._volume = volume

    def media_play(self):
        """Send play command."""
        self.fetch_data(command="pl_pause")
        self._state = STATE_PLAYING

    def media_pause(self):
        """Send pause command."""
        self.fetch_data(command="pl_pause")
        self._state = STATE_PAUSED

    def media_stop(self):
        """Send stop command."""
        self.fetch_data(command="pl_stop")
        self._state = STATE_IDLE
