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
"""Utilities for working with MPEG7 files

@motjuste
Created: 21-11-2017
"""
from __future__ import division, absolute_import, print_function
import warnings
import xml.etree.ElementTree as et
from six.moves import zip, reduce

from .py_utils import lowest_common_multiple

MPEG7_NAMESPACES = {
    "ns": "http://www.iais.fraunhofer.de/ifinder",
    "ns2": "urn:mpeg:mpeg7:schema:2004",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "mpeg7": "urn:mpeg:mpeg7:schema:2004",
    "ifinder": "http://www.iais.fraunhofer.de/ifinder"
}

NS2_TAGS = {
    "audiosegment": ".//ns2:AudioSegment",
    "timepoint": ".//ns2:MediaTimePoint",
    "duration": ".//ns2:MediaDuration",
    "descriptor": ".//ns2:AudioDescriptor[@xsi:type='SpokenContentType']",
    "speakerid": ".//ns:Identifier",
    "transcription": ".//ns:SpokenUnitVector",
    "confidence": ".//ns:ConfidenceVector",
    "speakerinfo": ".//ns:Speaker",
    "gender": "gender",
    "givenname": ".//ns2:GivenName",
}

MPEG7_TAGS = {
    "audiosegment": ".//mpeg7:AudioSegment",
    "timepoint": ".//mpeg7:MediaTimePoint",
    "duration": ".//mpeg7:MediaDuration",
    "descriptor": ".//mpeg7:AudioDescriptor[@xsi:type='ifinder:SpokenContentType']",
    "speakerid": ".//ifinder:Identifier",
    "transcription": ".//ifinder:SpokenUnitVector",
    "confidence": ".//ifinder:ConfidenceVector",
    "speakerinfo": ".//ifinder:Speaker",
    "gender": "gender",
    "givenname": ".//mpeg7:GivenName",
}


def parse_mpeg7(filepath, use_tags="ns"):  # pylint: disable=too-many-locals,too-complex
    """ Parse MPEG7 speech annotations into lists of data

    """
    tree = et.parse(filepath)
    root = tree.getroot()

    if use_tags == "mpeg7":
        tags = MPEG7_TAGS
    elif use_tags == "ns":
        tags = NS2_TAGS
    else:
        raise ValueError("Supported `use_tags` : 'mpeg7' and 'ns'.")

    # find all AudioSegments
    segments = root.findall(tags["audiosegment"], MPEG7_NAMESPACES)
    if not segments:
        raise ValueError("No AudioSegment tags found. Check your xml file.")

    starts_ends = []
    persecs = []
    speakerids = []
    genders = []
    givennames = []
    confidences = []
    transcriptions = []
    for i, s in enumerate(segments):
        try:
            start_end_persec, descriptor = _parse_segment(s, tags)
        except ValueError:
            print("Segment number :%d" % (i + 1))
            raise

        if descriptor is None:
            # NOTE: if there is not descriptor, there is no speech. Ignore!
            continue

        if start_end_persec[1] <= start_end_persec[0]:  # (end - start) <= 0
            msg = (
                "(end - start) <= 0 ignored for annotation at position "
                "{} with values {} in file:\n{}".format(i, start_end_persec, filepath)
            )

            warnings.warn(RuntimeWarning(msg))
            continue

        starts_ends.append(start_end_persec[:-1])
        persecs.append(start_end_persec[-1])

        try:
            sid, gen, gname, conf, tran = _parse_descriptor(descriptor, tags)
        except ValueError:
            print("Segment number:%d" % (i + 1))

        speakerids.append(sid)
        genders.append(gen)
        givennames.append(gname)
        confidences.append(conf)
        transcriptions.append(tran)

    starts_ends, persecs = _sanitize_starts_ends(starts_ends, persecs)

    return (
        starts_ends, persecs, speakerids, genders, givennames, confidences, transcriptions
    )


def _parse_segment(segment, tags):
    timepoint = segment.find(tags["timepoint"], MPEG7_NAMESPACES).text
    duration = segment.find(tags["duration"], MPEG7_NAMESPACES).text
    descriptor = segment.find(tags["descriptor"], MPEG7_NAMESPACES)

    if any(d is None for d in [timepoint, duration]):  #, descriptor]):
        raise ValueError("timepoint, duration or decriptor not found in segment")

    start_end_persec = _parse_timestring(timepoint, duration)

    return start_end_persec, descriptor


def _parse_timestring(timepoint, duration):
    tpt, tps = _parse_timepoint(timepoint)
    dur, dps = _parse_duration(duration)

    # bring them to the same persec before calculating end
    persec = lowest_common_multiple(tps, dps)
    tpt *= (persec // tps)
    return tpt, tpt + dur * (persec // dps), persec


def _parse_timepoint(timepoint):
    _, timepoint = timepoint.split('T')  # 'T' indicates the rest part is time
    hours, minutes, sec, timepoint = timepoint.split(':')

    # timepoint will have the nFN
    # n = number of fraction of seconds
    # N = the standard number of fractions per second
    val, persec = timepoint.split('F')

    res = int(hours) * 3600 +\
          int(minutes) * 60 +\
          int(sec)

    return res * int(persec) + int(val), int(persec)


def _parse_duration(duration):
    _, duration = duration.split('T')

    splits = [0] * 5
    for i, marker in enumerate(['H', 'M', 'S', 'N', 'F']):
        if marker in duration:
            value, duration = duration.split(marker)
            splits[i] = int(value)
        else:
            splits[i] = 0

    hours, minutes, sec, val, persec = splits
    res = int(hours) * 3600 +\
          int(minutes) * 60 +\
          int(sec)

    return res * int(persec) + int(val), int(
        persec
    )  # need to send separately as the float sum is not great


def _parse_descriptor(descriptor, tags):
    speakerid = descriptor.find(tags["speakerid"], MPEG7_NAMESPACES).text
    speakerinfo = descriptor.find(tags["speakerinfo"], MPEG7_NAMESPACES)
    transcription = descriptor.find(tags["transcription"], MPEG7_NAMESPACES).text
    confidence = descriptor.find(tags["confidence"], MPEG7_NAMESPACES).text

    gender = speakerinfo.get(tags["gender"])
    givenname = speakerinfo.find(tags["givenname"], MPEG7_NAMESPACES).text

    if any(x is None for x in [speakerid, gender, givenname, confidence, transcription]):
        raise ValueError("Some descriptor information is None / not found")

    return speakerid, gender, givenname, confidence, transcription


def _sanitize_starts_ends(starts_ends, persecs):
    """ Sanitize starts ends to be of the same samplerate (persec) """
    persec = reduce(lowest_common_multiple, set(persecs))
    return [
        (s * persec // p, e * persec // p) for (s, e), p in zip(starts_ends, persecs)
    ], persec
