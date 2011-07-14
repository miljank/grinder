# Copyright (c) 2011 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

"""
Active Object classes.
Protocol:
 Codes:
     0 = Normal Return
         retval = returned value
     1 = Raised Exception
         retval = raised exception
     2 = Logging Request
         retval = log-record
 Record:
   call  = (object, method, *args, **kwargs)
   log   = (logger, level, msg, args)
   reply = (code, retval, state)
"""

import os
import sys
import errno
import atexit
import logging
import cPickle as pickle
import traceback as tb
from subprocess import Popen, PIPE
from threading import RLock
from signal import SIGTERM


class Method:
    """
    Remote method stub.
    @ivar name: The method name.
    @type name: str
    @ivar object: An active object.
    @type object: L{ActiveObject}
    """
    
    def __init__(self, name, object):
        """
        @param name: The method name.
        @type name: str
        @param object: An active object.
        @type object: L{ActiveObject}
        """
        self.name = name
        self.object = object

    def abort(self):
        """
        Abort (kill) the active object child process.
        """
        self.object._ActiveObject__kill()

    def __call__(self, *args, **kwargs):
        """
        Method invocation using the active object.
        @param args: The argument list.
        @type args: list
        @param kwargs: The kwargs argument dict.
        @type kwargs: dict
        """
        return self.object(self, *args, **kwargs)
    

class ActiveObject:
    """
    An remote (active) object.
    Methods invoked in a child process.
    @ivar object: The wrapped object.
    @type object: object
    @ivar __child: The child process.
    @type __child: Process
    @ivar __mutex: Mutex to ensure serial RMI.
    @type __mutex: RLock
    """

    def __init__(self, object):
        """
        @param object: A I{real} object whos methods are invoked
            in the child process.
        @type object: object
        """
        self.object = object
        atexit.register(self.__kill)
        self.__child = None
        self.__mutex = RLock()
        self.__spawn()
        
    def __rmi(self, method, args, kwargs):
        """
<<<<<<< HEAD
        Remote Method invocation.
        The active object, method name and arguments are pickled and
        sent to the child on the stdin pipe.  Then, the result is read
        on the child stdout pipe.  See: Protocol.
        @param method: The method name.
        @type method: str
        @param args: The argument list.
        @type args: list
        @param kwargs: The kwargs argument dict.
        @type kwargs: dict
        """
        p = self.__child
        call = (self.object, method, args, kwargs)
        pickle.dump(call, p.stdin)
        p.stdin.flush()
        while True:
            code, retval, state = pickle.load(p.stdout)
            if code == 0:
                setstate(self.object, state)
                return retval
            if code == 1:
                raise Exception(retval)
            if code == 2:
                self.__logchild(*retval)
                
    def __logchild(self, name, level, msg, args):
        """
        Perform child logging request
        @param name: The logger name.
        @type name: str
        @param level: The logging level.
        @type level: str
        @param msg: The log message
        @type msg: str
        @param args: The argument list
        @type args: list
        """
        log = logging.getLogger(name)
        method = getattr(log, level)
        method(msg, *args)
    
    def __spawn(self):
        """
        Spawn the child process.
        """
        self.__child = Popen(
            (sys.executable, __file__),
            close_fds=True,
            stdin=PIPE,
            stdout=PIPE)
        
    def __respawn(self):
        """
        Respawn the child process.
        """
        self.__kill()
        self.__spawn()

    def __kill(self):
        """
        Kill the child process.
        Does not use Popen.kill() for python 2.4 compat.
        """
        if self.__child:
            pid = self.__child.pid
            self.__child = None
            kill(pid)

    def __lock(self):
        """
        Lock the object.
        """
        self.__mutex.acquire()

    def __unlock(self):
        """
        Unlock the object.
        """
        self.__mutex.release()

    def __call(self, method, args, kwargs):
        """
        Method invocation.
        An IOError indictes a broken pipe(s) between the parent and
        child process.  This usually indicates that the child has terminated.
        For robustness, we respawn the child and try again.  An EOFError and a
        __child = None, indicates the child was killed through the parent __kill().
        @param args: The argument list.
        @type args: list
        @param kwargs: The kwargs argument dict.
        @type kwargs: dict
        """
        retry = 3
        while True:
            try:
                return self.__rmi(method.name, args, kwargs)
            except EOFError, e:
                if not self.__child:
                    break # aborted
            except IOError, e:
                if retry:
                    self.__respawn()
                    retry -= 1
                else:
                    raise e
    
    def __call__(self, method, *args, **kwargs):
        """
        Method invocation.
        Mutexed to ensure serial access to the child.
        @param args: The argument list.
        @type args: list
        @param kwargs: The kwargs argument dict.
        @type kwargs: dict
        """
        self.__lock()
        try:
            if not self.__child:
                self.__spawn()
            return self.__call(method, args, kwargs)
        finally:
            self.__unlock()

    def __getattr__(self, name):
        """
        @return: A method stub.
        @rtype: L{Method}
        """
        if name.startswith('__') and name.endswith('__'):
            return self.__dict__[name]
        return Method(name, self)
    
    def __del__(self):
        """
        Clean up the child process.
        """
        self.__kill()
        
        
class Logger:
    """
    The remote logging proxy.
    @ivar name: The logger name.
    @type name: str
    """
    
    def __init__(self, name):
        """
        @param name: The logger name.
        @type name: str
        """
        self.name = name

    class Method:
        
        def __init__(self, logger, name):
            """
            The logging method stub.
            @param logger: The logger object.
            @type logger: L{Logger}
            @param name: The method name (level).
            @type name: str
            """
            self.logger = logger
            self.name = name
        
        def __call__(self, msg, *args, **kwargs):
            """
            Invoke the logging call.
            @param msg: The message to log.
            @type msg: object
            @param args: The argument list
            @type args: tuple
            @param kwargs: The keyword args.
            @type kwargs: dict
            """
            msg, args = \
                self.__processArgs(msg, args)
            msg, kwargs = \
                self.__processKeywords(msg, kwargs)  
            self.__send(msg, args)
            
        def __processArgs(self, msg, args):
            """
            Process the arguments.
            When (msg) is an exception, replace it with formatted
            message and concattenated traceback.
            @param msg: The message argument.
            @type msg: object
            @param args: The argument list.
            @type args: tuple
            @return: The processed (msg, args)
            @rtype: tuple 
            """
            arglist = []
            if isinstance(msg, Exception):
                msg = '\n'.join((str(msg), trace()))
            for arg in args:
                if isinstance(arg, Exception):
                    arg = '\n'.join((str(arg), trace()))
                arglist.append(arg)
            return (msg, arglist)
            
        def __processKeywords(self, msg, keywords):
            """
            Process the keyword arguments.
            When 'exc_info' is True, append the traceback information
            to the returned message.
            @param msg: The message argument.
            @type msg: object
            @param keywords: The keyword arguments.
            @type keywords: dict
            @return: The processed (msg, kwargs)
            @rtype: tuple 
            """
            exflag = keywords.pop('exc_info', 0)
            if exflag:
                msg = '\n'.join((msg, trace()))
            return (msg, keywords)
            
        def __send(self, msg, args):
            """
            Send the logging request to the parent.
            @type msg: object
            @param args: The argument list.
            @type args: tuple
            """
            lr = (self.logger.name,
                  self.name, 
                  msg,
                  args)
            pickle.dump((2, lr, {}), sys.stdout)
            sys.stdout.flush()
            
    def __getattr__(self, name):
        """
        @return: The method stub.
        @rtype: L{Logger.Method}
        """
        return self.Method(self, name)

    
def process():
    """
    Reads and processes RMI requests.
     Input: (object, method, args, kwargs)
    Output: (code, retval, state)
    See: Protocol.
    """
    code = 0
    state = {}
    try:
        call = pickle.load(sys.stdin)
        object = call[0]
        method = getattr(object, call[1])
        args = call[2]
        kwargs = call[3]
        retval = method(*args, **kwargs)
        state = getstate(object)
    except:
        code = 1
        retval = trace()
    result = (code, retval, state)
    pickle.dump(result, sys.stdout)
    sys.stdout.flush()
    
def getstate(object):
    key = '__getstate__'
    if hasattr(object, key):
        method = getattr(object, key)
        return method()
    else:
        return object.__dict__
    
def setstate(object, state):
    key = '__setstate__'
    if hasattr(object, key):
        method = getattr(object, key)
        method(state)
    else:
        object.__dict__.update(state)
        
def trace():
    info = sys.exc_info()
    return '\n'.join(tb.format_exception(*info))

def kill(pid, sig=SIGTERM):
    try:
        os.kill(pid, sig)
        os.waitpid(pid, os.WNOHANG)
    except OSError, e:
        if e.errno != errno.ESRCH:
            raise e

def main():
    logging.getLogger = Logger
    while True:
        process()
    
if __name__ == '__main__':
    main()
