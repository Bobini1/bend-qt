"""Canonical header spellings of supported signed 64-bit chrono durations."""
import re


def normalize(t):
    if t.get('pointers') or t.get('array') or t.get('name') != 'std::chrono::duration':
        return None
    match = re.fullmatch(r'(?:const\s+)?std::chrono::duration\s*<\s*(long(?:\s+long)?|qint64|(?:std::)?int64_t)\s*,\s*std::ratio\s*<\s*(\d+)\s*,\s*(\d+)\s*>\s*>\s*&?', t['cpp'])
    if not match: return None
    units = {(1,1000000000):'nanoseconds', (1,1000000):'microseconds',
             (1,1000):'milliseconds', (1,1):'seconds', (60,1):'minutes', (3600,1):'hours'}
    unit = units.get((int(match[2]), int(match[3])))
    if not unit: return None
    name = 'std::chrono::' + unit
    return dict(t, name=name, cpp=name, instantiations=[], container=False)
