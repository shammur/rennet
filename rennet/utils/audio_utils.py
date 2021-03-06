#  Copyright 2018 Fraunhofer IAIS. All rights reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""Utilities for working with audio.

@mojuste
Created: 18-08-2016
"""
from __future__ import print_function, division, absolute_import
import os
import warnings
from collections import namedtuple
import subprocess as sp
import numpy as np
import librosa as lr

from .py_utils import cvsecs

try:
    from subprocess import DEVNULL
except ImportError:
    DEVNULL = open(os.devnull, 'wb')  # FIXME: Okay to never close this?

AudioMetadata = namedtuple(
    'AudioMetadata',
    [
        'filepath',  # not guaranteed absolute, using user provided
        'format',  # may get converted if not WAV
        'samplerate',
        'nchannels',
        'seconds',  # duration in seconds, may not be exact beyond 1e-2
        'nsamples',  # may not be accurate if not WAV, since being derived from seconds
    ]
)


def which(executable):
    """ Check if executable is available on the system

    Works with Unix type systems and Windows
    NOTE: no changes are made to the executable's name, only path is added

    # Arguments
        executable: str name of the executable (with `.exe` for Windows)

    # Returns:
        False or executable: depending on if the executable is accessible
    """

    envdir_list = [os.curdir] + os.environ["PATH"].split(os.pathsep)

    for envdir in envdir_list:
        possible_path = os.path.join(envdir, executable)
        if os.path.isfile(possible_path) and os.access(possible_path, os.X_OK):
            return executable

    # executable was not found
    return False  # Sorry for type-stability


def get_codec():
    """ Get codec to use for the audio file

    Searches for existence of `FFMPEG` first, then `AVCONV`
    NOTE: `.exe` is appended to name if on Windows

    # Returns
        False or executable: bool or str : executable of the codec if available
    """
    return (
        which("ffmpeg.exe") if os.name == "nt" else (which("ffmpeg") or which("avconv"))
    )


def get_sph2pipe():
    """ Get the sph2pipe executable's path if available

    # Retruns
        False, or executable: bool or str : path to sph2pipe
    """
    return which("sph2pipe.exe") if os.name == "nt" else which("sph2pipe")


CODEC_EXEC = get_codec()  # NOTE: Available codec; False when none available


def read_wavefile_metadata(filepath):
    """ Read AudioMetadata of a WAV file without reading all of it

    Heavily depends on `scipy.io.wavfile`.

    # Arguments
        filepath: str: full path to the WAV file

    # Returns
        meta: AudioMetadata object (namedtuple): with information as:

    # Reference
        https://github.com/scipy/scipy/blob/master/scipy/io/wavfile.py#L116

    """
    import struct
    from scipy.io.wavfile import _read_riff_chunk, _read_fmt_chunk
    from scipy.io.wavfile import _skip_unknown_chunk

    fid = open(filepath, 'rb')

    def _read_n_samples(fid, big_endian, bits):
        if big_endian:
            fmt = '>i'
        else:
            fmt = '<i'

        size = struct.unpack(fmt, fid.read(4))[0]

        return size // (bits // 8)  # indicates total number of samples

    try:
        size, is_big_endian = _read_riff_chunk(fid)

        while fid.tell() < size:
            chunk = fid.read(4)
            if chunk == b'fmt ':
                fmt_chunk = _read_fmt_chunk(fid, is_big_endian)
                channels, samplerate = fmt_chunk[2:4]  # info relevant to us
                bits = fmt_chunk[6]
            elif chunk == b'data':
                n_samples = _read_n_samples(fid, is_big_endian, bits)
                break  # NOTE: break as now we have all info we need
            elif chunk in (b'JUNK', b'Fake', b'LIST', b'fact'):
                _skip_unknown_chunk(fid, is_big_endian)
            else:
                warnings.warn(
                    "Chunk (non-data) not understood, skipping it.", RuntimeWarning
                )
                _skip_unknown_chunk(fid, is_big_endian)
    finally:  # always close
        fid.close()

    return AudioMetadata(
        filepath=filepath,
        format='wav',
        samplerate=samplerate,
        nchannels=channels,
        seconds=(n_samples // channels) / samplerate,
        nsamples=n_samples // channels  # for one channel
    )


def read_sph_metadata(filepath):
    """Read metadata of SPHERE audio files
    TODO: [ ] Add documentation
    NOTE: Tested and developed specifically for the Fisher Dataset
    """
    filepath = os.path.abspath(filepath)
    fid = open(filepath, 'rb')

    try:
        # HACK: Going to read the header that is supposed to stop at
        # 'end_header'. If it is not found, I stop at 100 readlines anyway

        # First line gives the header type
        fid.seek(0)
        assert fid.readline().startswith(b'NIST'), "Unrecognized Sphere Header type"

        # The second line tells the header size
        _header_size = int(fid.readline().strip())

        # read the header lines based on the _header_size
        fid.seek(0)
        # Each info is on different lines (per dox)
        readlines = fid.read(_header_size).split(b'\n')

        # Start reading relevant metadata
        nsamples = None
        nchannels = None
        samplerate = None

        for line in readlines:
            splitline = line.split(b' ')
            info, data = splitline[0], splitline[-1]

            if info == b'sample_count':
                nsamples = int(data)
            elif info == b'channel_count':
                nchannels = int(data)
            elif info == b'sample_rate':
                samplerate = int(data)
            else:
                continue
    finally:
        fid.close()

    if any(x is None for x in [nsamples, nchannels, samplerate]):
        raise RuntimeError("The Sphere header was read, but some information was missing")
    else:
        return AudioMetadata(
            filepath=filepath,
            format='sph',
            samplerate=samplerate,
            nchannels=nchannels,
            seconds=nsamples / samplerate,
            nsamples=nsamples
        )


def read_audio_metadata_codec(filepath):  # pylint: disable=too-complex
    """Read metadata of audio using a codec
    TODO: [A] Add documentation
    """
    import re

    def _read_codec_error_output(filepath):
        command = [CODEC_EXEC, "-i", filepath]

        popen_params = {
            "bufsize": 10**5,
            "stdout": sp.PIPE,
            "stderr": sp.PIPE,
            "stdin": DEVNULL
        }

        if os.name == 'nt':
            popen_params["creationflags"] = 0x08000000

        proc = sp.Popen(command, **popen_params)
        proc.stdout.readline()
        proc.terminate()

        # Ref: http://stackoverflow.com/questions/19699367
        infos = proc.stderr.read().decode('ISO-8859-1')
        del proc

        return infos

    def _read_samplerate(line):
        try:
            match = re.search(" [0-9]* Hz", line)
            matched = line[match.start():match.end()]
            samplerate = int(matched[1:-3])
            return samplerate
        except:
            raise RuntimeError(
                "Failed to load sample rate of file %s from %s\n the infos from %s are \n%s"
                % (filepath, CODEC_EXEC, CODEC_EXEC, infos)
            )

    def _read_n_channels(line):
        try:
            match1 = re.search(" [0-9]* channels", line)

            if match1 is None:
                match2 = re.search(" stereo", line)
                match3 = re.search(" mono", line)
                if match2 is None and match3 is not None:
                    channels = 1
                elif match2 is not None and match3 is None:
                    channels = 2
                else:
                    raise RuntimeError()
            else:
                channels = int(line[match1.start() + 1:match1.end() - 9])

            return channels
        except:
            raise RuntimeError(
                "Failed to load n channels of file %s from %s\n the infos from %s are \n%s"
                % (filepath, CODEC_EXEC, CODEC_EXEC, infos)
            )

    def _read_duration(line):
        try:
            keyword = 'Duration: '
            line = [l for l in lines if keyword in l][0]
            match = re.findall("([0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9])", line)[0]
            duration_seconds = cvsecs(match)
            return duration_seconds
        except:
            raise RuntimeError(
                "Failed to load duration of file %s from %s\n the infos from %s are \n%s"
                % (filepath, CODEC_EXEC, CODEC_EXEC, infos)
            )

    # to throw error for FileNotFound
    # TODO: [A] test error when FileNotFound
    with open(filepath):
        pass

    if not get_codec():
        raise RuntimeError("No codec available")

    infos = _read_codec_error_output(filepath)
    lines = infos.splitlines()
    lines_audio = [l for l in lines if ' Audio: ' in l]
    if lines_audio == []:
        raise RuntimeError(
            "%s did not find audio in the file %s and produced infos\n%s" %
            (CODEC_EXEC, filepath, infos)
        )

    samplerate = _read_samplerate(lines_audio[0])
    channels = _read_n_channels(lines_audio[0])
    duration_seconds = _read_duration(lines)

    n_samples = int(duration_seconds * samplerate) + 1

    warnings.warn(
        "Metadata was read from %s, duration and number of samples may not be accurate" %
        CODEC_EXEC, RuntimeWarning
    )

    return AudioMetadata(
        filepath=filepath,
        format=os.path.splitext(filepath)[1][1:],  # extension after the dot
        samplerate=samplerate,
        nchannels=channels,
        seconds=duration_seconds,
        nsamples=n_samples
    )


def get_audio_metadata(filepath):
    """ Get the metadata for an audio file without reading all of it

    NOTE: Tested only on formats [wav, mp3, mp4, avi], only on macOS

    NOTE: for file formats other than wav, requires FFMPEG or AVCONV installed

    The idea is that getting just the sample rate for the audio in a media file
    should not require reading the entire file.

    The implementation for reading metadata for wav files REQUIRES scipy

    For other formats, the implementation parses ffmpeg or avconv (error) output to get the
    required information.

    # Arguments
        filepath: path to audio file

    # Returns
        samplerate: in Hz
    """

    # TODO: [ ] Do better reading of audiometadata
    try:
        return (
            read_sph_metadata(filepath)
            if filepath.lower().endswith('sph') else read_wavefile_metadata(filepath)
        )
    except ValueError:
        # Was not a wavefile
        if get_codec():
            return read_audio_metadata_codec(filepath)
        else:
            raise RuntimeError(
                "Neither FFMPEG or AVCONV was found, nor is file %s a valid WAVE file" %
                filepath
            )


def load_audio(filepath, samplerate=8000, mono=True, return_samplerate=False, **kwargs):
    """ Load an audio file supported by `librosa.load(...)`.

    Extra keyword arguments supported by `librosa.load(...)` are passed on.
    Interesting ones may include `offset`, `duration`, `res_type`. Check references.

    References
    ----------
    http://librosa.github.io/librosa/generated/librosa.core.load.html#librosa.core.load
    """
    data, sr = lr.core.load(filepath, sr=samplerate, mono=mono, **kwargs)
    data = data.T  # librosa loads data in shape (n, ) or (2, n), which is stupid
    return (data, sr) if return_samplerate else data


def powspectrogram(y, n_fft, hop_len, win_len=None, window='hann'):
    return np.abs(
        lr.stft(
            y,
            n_fft=n_fft,
            hop_length=hop_len,
            win_length=win_len,
            window=window,
            center=False
        )
    ).T**2.0


def melspectrogram(  # pylint: disable=too-many-arguments
        powspec=None,
        sr=8000,
        y=None,
        n_fft=256,
        hop_len=80,
        win_len=None,
        window='hann',
        n_mels=64,
        **kwargs):
    if powspec is None:
        powspec = powspectrogram(y, n_fft, hop_len, win_len=win_len, window=window).T

    mel_basis = lr.filters.mel(sr, n_fft, n_mels=n_mels, **kwargs)

    return np.dot(mel_basis, powspec).T


def logmelspectrogram(  # pylint: disable=too-many-arguments
        melspec=None,
        amin=1e-8,
        y=None,
        powspec=None,
        sr=8000,
        n_fft=256,
        hop_len=80,
        win_len=None,
        window='hann',
        n_mels=64,
        **kwargs):
    if melspec is None:
        melspec = melspectrogram(
            y=y,
            powspec=powspec,
            sr=sr,
            n_fft=n_fft,
            hop_len=hop_len,
            win_len=win_len,
            window=window,
            n_mels=n_mels,
            **kwargs
        )

    return np.log10(np.maximum(amin, melspec))
