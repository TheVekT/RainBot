import asyncio
import errno
import subprocess
import unittest
from unittest.mock import patch

from modules.scraper_core import browser_cleanup as module
from modules.scraper_core import base_parser as parser


def emfile():
    return OSError(errno.EMFILE, 'Too many open files')


class Stream:
    def __init__(self, error=None): self.error, self.closed = error, 0
    def close(self):
        self.closed += 1
        if self.error: raise self.error


class Process:
    def __init__(self, error=None):
        self.stdin, self.stdout, self.stderr = Stream(), Stream(), Stream()
        self.error, self.waited, self.killed = error, 0, 0
    def wait(self, timeout):
        self.waited += 1
        if self.error: raise self.error
    def kill(self): self.killed += 1


class Executor:
    def __init__(self, error=None): self.error, self.closed = error, 0
    def close(self):
        self.closed += 1
        if self.error: raise self.error


class Driver:
    def __init__(self, error=None):
        self.error, self.quit_calls = error, 0
        self.browser_pid = None
        self.service = type('Service', (), {})()
        self.service.process = Process()
        self.command_executor = Executor()
    def quit(self):
        self.quit_calls += 1
        if self.error: raise self.error


async def fake_sleep(_): pass


class TestCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_only_owned_browser_children_are_killed(self):
        class Child:
            def __init__(self, name): self.process_name, self.killed = name, 0
            def name(self): return self.process_name
            def kill(self): self.killed += 1
        browser, driver, unrelated_child = Child('chromium'), Child('undetected_chro'), Child('python')
        other_browser = Child('chromium')
        p = parser.RainParser()
        with patch.object(module.asyncio, 'sleep', fake_sleep), \
             patch.object(p, '_owned_browser_processes', return_value=[browser, driver, unrelated_child]), \
             patch.object(module.psutil, 'process_iter', side_effect=AssertionError('global process scan')):
            await p.close_browsers()
        self.assertEqual((browser.killed, driver.killed, unrelated_child.killed, other_browser.killed), (1, 1, 0, 0))

    async def test_process_tree_is_captured_before_driver_quit(self):
        p = parser.RainParser()
        calls = []
        async def quit_driver(): calls.append('quit')
        def descendants(): calls.append('capture'); return []
        with patch.object(module.asyncio, 'sleep', fake_sleep), \
             patch.object(p, 'driver_quit', side_effect=quit_driver), \
             patch.object(p, '_owned_browser_processes', side_effect=descendants):
            await p.close_browsers()
        self.assertEqual(calls, ['capture', 'quit'])

    async def test_success_and_double_cleanup(self):
        p=parser.RainParser(); d=Driver(); p.driver=d
        with patch.object(module.asyncio, 'sleep', fake_sleep), patch.object(p, '_owned_browser_processes', return_value=[]):
            await p.close_browsers()
            await p.close_browsers()
        self.assertIsNone(p.driver)
        self.assertEqual(d.quit_calls,1)
        self.assertEqual(d.service.process.waited,1)
        self.assertEqual(d.command_executor.closed,1)
        self.assertTrue(all(x.closed==1 for x in (d.service.process.stdin,d.service.process.stdout,d.service.process.stderr)))

    async def test_emfile_not_swallowed_and_other_resources_closed(self):
        for origin in ('quit','wait','stdin','executor'):
            with self.subTest(origin=origin):
                p=parser.RainParser(); d=Driver(); p.driver=d
                if origin=='quit': d.error=emfile()
                elif origin=='wait': d.service.process.error=emfile()
                elif origin=='stdin': d.service.process.stdin.error=emfile()
                else: d.command_executor.error=emfile()
                with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[]):
                    with self.assertRaises(OSError) as caught: await p.close_browsers()
                self.assertEqual(caught.exception.errno,errno.EMFILE)
                self.assertEqual(d.command_executor.closed,1)
                self.assertTrue(all(x.closed==1 for x in (d.service.process.stdin,d.service.process.stdout,d.service.process.stderr)))

    async def test_emfile_during_process_enumeration_propagates(self):
        p=parser.RainParser()
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',side_effect=emfile()):
            with self.assertRaises(OSError) as caught: await p.close_browsers()
        self.assertEqual(caught.exception.errno,errno.EMFILE)

    async def test_emfile_during_sweep_and_browser_reap_propagates(self):
        class SweepProc:
            pid=456
            def name(self): return 'chromium'
            def kill(self): raise emfile()
        p=parser.RainParser()
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[SweepProc()]):
            with self.assertRaises(OSError) as caught: await p.close_browsers()
        self.assertEqual(caught.exception.errno,errno.EMFILE)
        class Browser:
            def is_running(self): return True
            def ppid(self): return module.os.getpid()
            def wait(self,timeout): raise emfile()
        p=parser.RainParser();p._pending_browser_reap.append(Browser())
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[]):
            with self.assertRaises(OSError) as caught: await p.close_browsers()
        self.assertEqual(caught.exception.errno,errno.EMFILE)

    async def test_timeout_kills_and_retries_wait(self):
        p=parser.RainParser(); d=Driver(); p.driver=d
        calls=[]
        def wait(timeout):
            calls.append(timeout)
            if len(calls)==1: raise subprocess.TimeoutExpired('driver', timeout)
        d.service.process.wait=wait
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[]):
            await p.close_browsers()
        self.assertEqual(d.service.process.killed,1)
        self.assertEqual(calls,[3,3])

    async def test_unrelated_browser_pid_is_never_reaped(self):
        p=parser.RainParser();d=Driver();p.driver=d;d.browser_pid=1234
        proc=type('P',(),{'ppid':lambda self: -1})()
        with patch.object(module.psutil,'Process',return_value=proc): await p.driver_quit()
        self.assertEqual(p._pending_browser_reap,[])

    async def test_browser_reap_timeout_retained_and_retried(self):
        class Child:
            def __init__(self): self.calls=0
            def is_running(self): return True
            def ppid(self): return module.os.getpid()
            def wait(self,timeout):
                self.calls+=1
                if self.calls==1: raise module.psutil.TimeoutExpired(timeout, pid=1)
        p=parser.RainParser(); child=Child(); p._remember_browser_for_reap(child)
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[]):
            await p.close_browsers()
            self.assertEqual(p._pending_browser_reap,[child])
            await p.close_browsers()
        self.assertEqual(child.calls,2)
        self.assertEqual(p._pending_browser_reap,[])

    async def test_reap_backlog_is_bounded_and_each_pass_is_bounded(self):
        class Child:
            def __init__(self): self.calls=0
            def is_running(self): return True
            def ppid(self): return module.os.getpid()
            def wait(self,timeout):
                self.calls+=1
                raise module.psutil.TimeoutExpired(timeout,pid=1)
        p=parser.RainParser(); children=[Child() for _ in range(33)]
        with self.assertLogs(module.logger,level='WARNING'):
            for child in children: p._remember_browser_for_reap(child)
        self.assertEqual(len(p._pending_browser_reap),32)
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[]):
            await p.close_browsers()
        self.assertEqual(sum(x.calls for x in children),4)
        self.assertEqual(len(p._pending_browser_reap),32)
        self.assertIs(p._pending_browser_reap[0],children[4])

    async def test_child_changed_owner_is_not_waited(self):
        class Child:
            def __init__(self): self.calls=0
            def is_running(self): return True
            def ppid(self): return -1
            def wait(self, timeout): self.calls+=1
        p=parser.RainParser(); child=Child(); p._remember_browser_for_reap(child)
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[]):
            await p.close_browsers()
        self.assertEqual(p._pending_browser_reap,[])
        self.assertEqual(child.calls,0)

    async def test_emfile_at_browser_launch_is_fatal_and_flag_resets(self):
        p=parser.RainParser()
        with patch.object(module.asyncio,'sleep',fake_sleep), patch.object(p,'_owned_browser_processes',return_value=[]), \
             patch.object(p,'_find_browser_binary',return_value='/usr/bin/chromium'), \
             patch.object(p,'_browser_major_version',return_value=120), patch.object(parser,'_OwnedChrome',side_effect=emfile()):
            with self.assertRaises(OSError) as caught: await p.restart_browser()
        self.assertEqual(caught.exception.errno,errno.EMFILE)
        self.assertFalse(p.restarting_browser)


if __name__=='__main__': unittest.main(verbosity=2)
