class Region(object):
    def __init__(self):
        super(Region, self).__init__()

        self.chunk_offsets = []
        self.timestamps = []
        self.chunks = {}
