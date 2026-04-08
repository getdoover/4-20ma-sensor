from pydoover.tags import Tag, Tags


class Sensor420maTags(Tags):
    value = Tag("number", default=None)
    raw_value = Tag("number", default=None)
    polling_frequency = Tag("number", default=None)
