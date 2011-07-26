import pycurl
import os
import logging

LOG = logging.getLogger("grinder.WriteFunction")

class WriteFunction(object):
    """ utility callback to acumulate response"""
    def __init__(self, path, size=None):
        """
        @param path: path to where the file is written to disk.
        @type path: str
        @param size: file size if available to compare.
        @type size: int
        """
        self.wfile = path
        self.size = size
        self.fp = None
        self.offset = 0
        self.chunk_read = 0
        self.setup()

    def setup(self):
        if os.path.exists(self.wfile):
            self.offset = self.get_offset()
            LOG.debug("File exists; offset at %s" % self.offset)
        self.fp = open(self.wfile, 'a+')
        self.chunk_read = self.offset
        
    def callback(self, chunk):
        """
        @param chunk: data chunk buffer to write or append to a file object
        @type chunk: str
        """
        LOG.debug("processing chunk %s" % len(chunk))
        self.chunk_read += len(chunk)
        if self.size and self.size == self.offset:
            # "File already exists with right size
            return
        if self.offset <= self.chunk_read:
            self.fp.seek(self.offset)
        self.fp.write(chunk)
        LOG.debug("Total chunk size read %s" % self.chunk_read)

    def get_offset(self):
        self.offset = os.stat(self.wfile).st_size
        return self.offset

    def cleanup(self):
        self.fp.close()
        self.offset = 0
        self.chunk_read = 0

if __name__ == "__main__":
    wf = WriteFunction("/tmp/test.iso", 3244032)
    curl = pycurl.Curl()
    curl.setopt(curl.URL, "http://repos.fedorapeople.org/repos/pulp/pulp/demo_repos/test_file_repo/test3.iso")
    print "OFFSET", wf.offset
    curl.setopt(pycurl.RESUME_FROM, wf.offset)
    curl.setopt(curl.BUFFERSIZE, 10240)
    curl.setopt(curl.WRITEFUNCTION, wf.callback)
    curl.perform()
    wf.cleanup()
    print os.stat("/tmp/test.iso").st_size
    assert(3244032 == os.stat("/tmp/test.iso").st_size)