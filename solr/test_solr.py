# (C) Datadog, Inc. 2010-2016
# All rights reserved
# Licensed under Simplified BSD License (see LICENSE)

# stdlib
import threading
import time
from types import ListType
import unittest
import mock
import os

# 3p
from nose.plugins.attrib import attr
import logging

# project
from aggregator import MetricsAggregator
from tests.checks.common import Fixtures


LOG_INFO = {
    'log_to_event_viewer': False,
    'log_to_syslog': False,
    'syslog_host': None,
    'syslog_port': None,
    'log_level': logging.INFO,
    'disable_file_logging': True,
    'collector_log_file': '/var/log/datadog/collector.log',
    'forwarder_log_file': '/var/log/datadog/forwarder.log',
    'dogstatsd_log_file': '/var/log/datadog/dogstatsd.log',
    'jmxfetch_log_file': '/var/log/datadog/jmxfetch.log',
    'go-metro_log_file': '/var/log/datadog/go-metro.log',
}

with mock.patch('config.get_logging_config', return_value=LOG_INFO):
    from dogstatsd import Server
    from jmxfetch import JMXFetch


STATSD_PORT = 8127

class DummyReporter(threading.Thread):
    def __init__(self, metrics_aggregator):
        threading.Thread.__init__(self)
        self.finished = threading.Event()
        self.metrics_aggregator = metrics_aggregator
        self.interval = 10
        self.metrics = None
        self.finished = False
        self.start()

    def run(self):
        while not self.finished:
            time.sleep(self.interval)
            self.flush()

    def flush(self):
        metrics = self.metrics_aggregator.flush()
        if metrics:
            self.metrics = metrics


@attr(requires='solr')
class JMXTestCase(unittest.TestCase):
    def setUp(self):
        aggregator = MetricsAggregator("test_host")
        self.server = Server(aggregator, "localhost", STATSD_PORT)
        self.reporter = DummyReporter(aggregator)

        self.t1 = threading.Thread(target=self.server.start)
        self.t1.start()

        fixture_dir = os.path.join(os.path.dirname(__file__), 'ci')
        confd_path = Fixtures.directory(sdk_dir=fixture_dir)
        self.jmx_daemon = JMXFetch(confd_path, {'dogstatsd_port': STATSD_PORT})
        self.t2 = threading.Thread(target=self.jmx_daemon.run)
        self.t2.start()

    def tearDown(self):
        self.server.stop()
        self.reporter.finished = True
        self.jmx_daemon.terminate()

    def testTomcatMetrics(self):
        count = 0
        while self.reporter.metrics is None:
            time.sleep(1)
            count += 1
            if count > 25:
                raise Exception("No metrics were received in 25 seconds")

        metrics = self.reporter.metrics

        self.assertTrue(isinstance(metrics, ListType))
        self.assertTrue(len(metrics) > 8, metrics)
        self.assertEquals(len([t for t in metrics if 'instance:solr_instance' in t['tags'] and t['metric'] == "jvm.thread_count"]), 1, metrics)
        self.assertTrue(len([t for t in metrics if "jvm." in t['metric'] and 'instance:solr_instance' in t['tags']]) > 4, metrics)
        self.assertTrue(len([t for t in metrics if "solr." in t['metric'] and 'instance:solr_instance' in t['tags']]) > 4, metrics)
