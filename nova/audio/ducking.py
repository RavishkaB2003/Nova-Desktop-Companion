"""
Project NOVA - Windows Audio Ducking Manager
Attenuates background OS/application audio during active speech recognition (FR-005).
Implemented using Windows Core Audio COM interfaces (IAudioEndpointVolume).
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def play_audio_chime(chime_type: str = "wake", async_play: bool = True) -> bool:
    """
    Play non-blocking audio feedback chime (FR-004).
    Chime patterns:
    - 'wake': rising tone sequence (D5 -> A5, 587Hz -> 880Hz)
    - 'sleep': falling tone sequence (880Hz -> 587Hz)
    - 'error': low alert pulse (440Hz -> 330Hz)
    - 'acknowledge': short confirmation (880Hz)
    """
    def _play() -> None:
        try:
            import winsound

            if chime_type == "wake":
                winsound.Beep(587, 80)
                winsound.Beep(880, 100)
            elif chime_type == "sleep":
                winsound.Beep(880, 80)
                winsound.Beep(587, 100)
            elif chime_type == "error":
                winsound.Beep(440, 100)
                winsound.Beep(330, 120)
            else:  # acknowledge
                winsound.Beep(880, 80)
        except Exception as exc:
            logger.debug("Audio chime playback unavailable (headless or muted): %s", exc)

    if async_play:
        t = threading.Thread(target=_play, name=f"Chime-{chime_type}", daemon=True)
        t.start()
        return True
    else:
        _play()
        return True

# Windows Core Audio GUIDs
CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioEndpointVolume = "{5CDF2C82-841E-4546-9722-0CF74078229A}"
IID_IMMDevice = "{D666063F-1587-4E43-81F1-B948E807363F}"

# Default ducking ratio: attenuate to 25% of current volume
DEFAULT_DUCK_RATIO = 0.25


class AudioDuckingManager:
    """
    Manages attenuation and restoration of Windows system master audio.
    Guarantees thread-safe, idempotent ducking and safe headless fallback.
    """

    def __init__(self, duck_ratio: float = DEFAULT_DUCK_RATIO) -> None:
        self._duck_ratio = max(0.0, min(1.0, duck_ratio))
        self._lock = threading.RLock()
        self._is_ducked = False
        self._original_volume: Optional[float] = None
        self._volume_interface = None
        self._com_initialized = False

        self._init_endpoint_volume()

    def _init_endpoint_volume(self) -> None:
        """Attempt to bind to Windows Core Audio endpoint volume interface."""
        try:
            from ctypes import POINTER, byref, c_float, c_int, c_long, c_void_p
            import comtypes
            from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

            guid_device_enum = GUID(CLSID_MMDeviceEnumerator)
            guid_device_enum_iface = GUID(IID_IMMDeviceEnumerator)
            guid_endpoint_vol = GUID(IID_IAudioEndpointVolume)
            guid_imm_device = GUID(IID_IMMDevice)

            class IAudioEndpointVolume(IUnknown):
                _iid_ = guid_endpoint_vol
                _methods_ = [
                    COMMETHOD([], HRESULT, "RegisterControlChangeNotify", (["in"], c_void_p, "pNotify")),
                    COMMETHOD([], HRESULT, "UnregisterControlChangeNotify", (["in"], c_void_p, "pNotify")),
                    COMMETHOD([], HRESULT, "GetChannelCount", (["out"], POINTER(c_int), "pnChannelCount")),
                    COMMETHOD([], HRESULT, "SetMasterVolumeLevel", (["in"], c_float, "fLevelDB"), (["in"], POINTER(GUID), "pguidEventContext")),
                    COMMETHOD([], HRESULT, "SetMasterVolumeLevelScalar", (["in"], c_float, "fLevel"), (["in"], POINTER(GUID), "pguidEventContext")),
                    COMMETHOD([], HRESULT, "GetMasterVolumeLevel", (["out"], POINTER(c_float), "pfLevelDB")),
                    COMMETHOD([], HRESULT, "GetMasterVolumeLevelScalar", (["out"], POINTER(c_float), "pfLevel")),
                    COMMETHOD([], HRESULT, "SetChannelVolumeLevel", (["in"], c_int, "nChannel"), (["in"], c_float, "fLevelDB"), (["in"], POINTER(GUID), "pguidEventContext")),
                    COMMETHOD([], HRESULT, "SetChannelVolumeLevelScalar", (["in"], c_int, "nChannel"), (["in"], c_float, "fLevel"), (["in"], POINTER(GUID), "pguidEventContext")),
                    COMMETHOD([], HRESULT, "GetChannelVolumeLevel", (["in"], c_int, "nChannel"), (["out"], POINTER(c_float), "pfLevelDB")),
                    COMMETHOD([], HRESULT, "GetChannelVolumeLevelScalar", (["in"], c_int, "nChannel"), (["out"], POINTER(c_float), "pfLevel")),
                    COMMETHOD([], HRESULT, "SetMute", (["in"], c_int, "bMute"), (["in"], POINTER(GUID), "pguidEventContext")),
                    COMMETHOD([], HRESULT, "GetMute", (["out"], POINTER(c_int), "pbMute")),
                    COMMETHOD([], HRESULT, "GetVolumeStepInfo", (["out"], POINTER(c_int), "pnStep"), (["out"], POINTER(c_int), "pnStepCount")),
                    COMMETHOD([], HRESULT, "VolumeStepUp", (["in"], POINTER(GUID), "pguidEventContext")),
                    COMMETHOD([], HRESULT, "VolumeStepDown", (["in"], POINTER(GUID), "pguidEventContext")),
                    COMMETHOD([], HRESULT, "QueryHardwareSupport", (["out"], POINTER(c_int), "pdwHardwareSupportMask")),
                    COMMETHOD([], HRESULT, "GetVolumeRange", (["out"], POINTER(c_float), "pflVolumeMindB"), (["out"], POINTER(c_float), "pflVolumeMaxdB"), (["out"], POINTER(c_float), "pflVolumeIncrementdB")),
                ]

            class IMMDevice(IUnknown):
                _iid_ = guid_imm_device
                _methods_ = [
                    COMMETHOD([], HRESULT, "Activate",
                        (["in"], POINTER(GUID), "iid"),
                        (["in"], c_long, "dwClsCtx"),
                        (["in"], c_void_p, "pActivationParams"),
                        (["out"], POINTER(POINTER(IAudioEndpointVolume)), "ppInterface")),
                ]

            class IMMDeviceEnumerator(IUnknown):
                _iid_ = guid_device_enum_iface
                _methods_ = [
                    COMMETHOD([], HRESULT, "EnumAudioEndpoints",
                        (["in"], c_int, "dataFlow"),
                        (["in"], c_long, "dwStateMask"),
                        (["out"], POINTER(c_void_p), "ppDevices")),
                    COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint",
                        (["in"], c_int, "dataFlow"),
                        (["in"], c_int, "role"),
                        (["out"], POINTER(POINTER(IMMDevice)), "ppEndpoint")),
                ]

            try:
                comtypes.CoInitialize()
                self._com_initialized = True
            except Exception:
                pass

            enumerator = comtypes.CoCreateInstance(
                guid_device_enum,
                IMMDeviceEnumerator,
                comtypes.CLSCTX_INPROC_SERVER,
            )
            # eRender = 0, eMultimedia = 1
            endpoint = enumerator.GetDefaultAudioEndpoint(0, 1)
            self._volume_interface = endpoint.Activate(
                byref(guid_endpoint_vol),
                comtypes.CLSCTX_INPROC_SERVER,
                None,
            )
            logger.info("Windows Core Audio Ducking endpoint interface bound successfully.")
        except Exception as exc:
            logger.warning("Core Audio initialization unavailable (running headless or non-Windows): %s", exc)
            self._volume_interface = None

    @property
    def is_ducked(self) -> bool:
        with self._lock:
            return self._is_ducked

    def get_current_volume(self) -> Optional[float]:
        """Returns the current master volume scalar (0.0 to 1.0) or None if unavailable."""
        with self._lock:
            if not self._volume_interface:
                return self._original_volume if self._original_volume is not None else 1.0
            try:
                return float(self._volume_interface.GetMasterVolumeLevelScalar())
            except Exception as exc:
                logger.debug("Failed to read master volume: %s", exc)
                return None

    def duck(self) -> bool:
        """
        Attenuate system audio to duck_ratio * current volume.
        Idempotent: Subsequent calls while ducked preserve the original baseline volume.
        """
        with self._lock:
            if self._is_ducked:
                return True

            if not self._volume_interface:
                # Headless/mock mode
                self._original_volume = self._original_volume or 1.0
                self._is_ducked = True
                logger.debug("Ducking simulated in headless environment.")
                return True

            try:
                current_vol = float(self._volume_interface.GetMasterVolumeLevelScalar())
                self._original_volume = current_vol
                ducked_vol = max(0.0, min(1.0, current_vol * self._duck_ratio))
                self._volume_interface.SetMasterVolumeLevelScalar(ducked_vol, None)
                self._is_ducked = True
                logger.info("Audio ducked: %.2f -> %.2f", current_vol, ducked_vol)
                return True
            except Exception as exc:
                logger.error("Failed to duck audio: %s", exc)
                return False

    def unduck(self) -> bool:
        """
        Restore system audio to the baseline volume before ducking was engaged.
        Idempotent: Calling unduck when not ducked is a no-op.
        """
        with self._lock:
            if not self._is_ducked:
                return True

            if not self._volume_interface:
                # Headless/mock mode
                self._is_ducked = False
                logger.debug("Unducking simulated in headless environment.")
                return True

            try:
                if self._original_volume is not None:
                    self._volume_interface.SetMasterVolumeLevelScalar(self._original_volume, None)
                    logger.info("Audio restored to original volume: %.2f", self._original_volume)
                self._is_ducked = False
                self._original_volume = None
                return True
            except Exception as exc:
                logger.error("Failed to unduck audio: %s", exc)
                return False
