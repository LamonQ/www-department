# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import unittest
from email import message_from_bytes

from trac.core import Component, implements
from trac.notification.api import (
    IEmailAddressResolver, IEmailSender, INotificationFormatter,
    INotificationSubscriber, NotificationEvent, NotificationSystem,
)
from trac.notification.mail import RecipientMatcher
from trac.notification.model import Subscription
from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import _fixup_cc_list
from trac.util.datefmt import datetime_now, utc
from trac.util.html import escape
from trac.web.session import DetachedSession


class TestEmailSender(Component):

    implements(IEmailSender)

    def __init__(self):
        self.history = []

    def send(self, from_addr, recipients, message):
        self.history.append((from_addr, recipients,
                             message_from_bytes(message)))


class TestFormatter(Component):

    implements(INotificationFormatter)

    def get_supported_styles(self, transport):
        if transport == 'email':
            yield 'text/plain', 'test'
            yield 'text/html', 'test'

    def format(self, transport, style, event):
        if transport != 'email':
            return
        text = event.target.text
        if style == 'text/plain':
            if 'raise-text-plain' in text:
                raise ValueError()
            return str(text)
        if style == 'text/html':
            if 'raise-text-html' in text:
                raise ValueError()
            return '<p>%s</p>' % escape(text)


class TestSubscriber(Component):

    implements(INotificationSubscriber)

    def _find_subscriptions(self):
        klass = self.__class__.__name__
        return Subscription.find_by_class(self.env, klass)

    def matches(self, event):
        if event.realm == 'test':
            for model in self._find_subscriptions():
                yield model.subscription_tuple()

    def description(self):
        return self.__class__.__name__

    def requires_authentication(self):
        return False

    def default_subscriptions(self):
        return ()


class TestEmailAddressResolver(Component):

    implements(IEmailAddressResolver)

    def get_address_for_session(self, sid, authenticated):
        if authenticated == 1:
            return '%s@example.net' % sid


class TestNotificationEvent(NotificationEvent): pass


class TestModel(object):

    realm = 'test'

    def __init__(self, text):
        self.text = text


class EmailDistributorTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.*', TestEmailSender,
                                           TestFormatter, TestSubscriber,
                                           TestEmailAddressResolver])
        self.config = config = self.env.config
        config.set('notification', 'smtp_from', 'trac@example.org')
        config.set('notification', 'smtp_enabled', 'enabled')
        config.set('notification', 'smtp_always_cc', 'cc@example.org')
        config.set('notification', 'smtp_always_bcc', 'bcc@example.org')
        config.set('notification', 'email_sender', 'TestEmailSender')
        config.set('notification', 'email_address_resolvers',
                   'SessionEmailResolver,TestEmailAddressResolver')
        self.sender = TestEmailSender(self.env)
        self.notsys = NotificationSystem(self.env)
        with self.env.db_transaction:
            self._add_session('foo', email='foo@example.org')
            self._add_session('bar', email='bar@example.org',
                              name="Bäŕ's name")
            self._add_session('baz', name='Baz')
            self._add_session('qux', tz='UTC')
            self._add_session('corge', email='corge-mail')

    def tearDown(self):
        self.env.reset_db()

    def _notify_event(self, text, category='created', time=None, author=None):
        self.sender.history[:] = ()
        event = TestNotificationEvent('test', category, TestModel(text),
                                      time or datetime_now(utc), author=author)
        self.notsys.notify(event)

    def _add_session(self, sid, values=None, **attrs):
        session = DetachedSession(self.env, sid)
        if values is not None:
            attrs.update(values)
        for name, value in attrs.items():
            session[name] = value
        session.save()

    def _add_subscription(self, **kwargs):
        subscription = {'sid': None, 'authenticated': 1, 'distributor': 'email',
                        'format': 'text/plain', 'adverb': 'always',
                        'class': 'TestSubscriber'}
        subscription.update(kwargs)
        Subscription.add(self.env, subscription)

    def test_smtp_disabled(self):
        self.env.config.set('notification', 'smtp_enabled', 'disabled')
        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='bar')
        self._notify_event('blah')
        self.assertEqual([], self.sender.history)

    def _assert_mail(self, message, content_type, body):
        self.assertNotIn('Bcc', message)
        self.assertEqual('multipart/related', message.get_content_type())
        payload = list(message.get_payload())
        self.assertEqual([content_type],
                         [p.get_content_type() for p in payload])
        self.assertEqual([body], [p.get_payload().rstrip('\n')
                                  for p in payload])

    def _assert_alternative_mail(self, message, body_plain, body_html):
        self.assertNotIn('Bcc', message)
        self.assertEqual('multipart/related', message.get_content_type())
        payload = list(message.get_payload())
        self.assertEqual(['multipart/alternative'],
                         [p.get_content_type() for p in payload])
        alternative = list(payload[0].get_payload())
        self.assertEqual(['text/plain', 'text/html'],
                         [p.get_content_type() for p in alternative])
        self.assertEqual([body_plain, body_html],
                         [p.get_payload().rstrip('\n') for p in alternative])

    def test_plain(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='bar')
            self._add_subscription(sid='baz')
            self._add_subscription(sid='qux')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual({'foo@example.org', 'bar@example.org',
                          'baz@example.net', 'qux@example.net',
                          'cc@example.org', 'bcc@example.org'},
                         set(recipients))
        self._assert_mail(message, 'text/plain', 'blah')

    def test_html(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/html')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(2, len(history))
        for from_addr, recipients, message in history:
            if 'foo@example.org' in recipients:
                self.assertEqual('trac@example.org', from_addr)
                self.assertEqual(['foo@example.org'], recipients)
                self._assert_alternative_mail(message, 'blah',
                                              '<p>blah</p>')
            if 'cc@example.org' in recipients:
                self.assertEqual('trac@example.org', from_addr)
                self.assertEqual({'cc@example.org', 'bcc@example.org'},
                                 set(recipients))
                self._assert_mail(message, 'text/plain', 'blah')

    def test_plain_and_html(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/plain')
            self._add_subscription(sid='bar', format='text/html')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(2, len(history))
        for from_addr, recipients, message in history:
            if 'foo@example.org' in recipients:
                self.assertEqual(
                    {'foo@example.org', 'cc@example.org', 'bcc@example.org'},
                    set(recipients))
                self._assert_mail(message, 'text/plain', 'blah')
            if 'bar@example.org' in recipients:
                self.assertEqual(['bar@example.org'], recipients)
                self._assert_alternative_mail(message, 'blah',
                                              '<p>blah</p>')

    def test_formats_in_session_and_tracini(self):
        self.config.set('notification', 'smtp_always_cc', 'bar,quux')
        self.config.set('notification', 'smtp_always_bcc', '')
        self.config.set('notification', 'default_format.email', 'text/html')
        with self.env.db_transaction:
            for user in ('foo', 'bar', 'baz', 'qux', 'quux'):
                self._add_session(user, email='%s@example.org' % user)
            self._add_subscription(sid='foo', format='text/plain')
            # bar - no subscriptions
            self._add_session('bar',
                              {'notification.format.email': 'text/plain'})
            self._add_subscription(sid='baz', format='text/plain')
            self._add_session('baz',
                              {'notification.format.email': 'text/html'})
            self._add_subscription(sid='qux', format='text/html')
            self._add_session('qux',
                              {'notification.format.email': 'text/plain'})
            # quux - no subscriptions and no preferred format in session
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(2, len(history))
        for from_addr, recipients, message in history:
            self.assertEqual('trac@example.org', from_addr)
            recipients = sorted(recipients)
            if 'bar@example.org' in recipients:
                self.assertEqual(['bar@example.org', 'baz@example.org',
                                  'foo@example.org'], recipients)
                self._assert_mail(message, 'text/plain', 'blah')
            if 'qux@example.org' in recipients:
                self.assertEqual(['quux@example.org', 'qux@example.org'],
                                 recipients)
                self._assert_alternative_mail(message, 'blah',
                                              '<p>blah</p>')

    def test_broken_plain_formatter(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/plain')
            self._add_subscription(sid='bar', format='text/html')
        self._notify_event('raise-text-plain')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual(['bar@example.org'], recipients)
        self._assert_mail(message, 'text/html', '<p>raise-text-plain</p>')

    def test_broken_html_formatter(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/html')
            self._add_subscription(sid='bar', format='text/plain')
        self._notify_event('raise-text-html')

        # fallback to text/plain
        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual({'foo@example.org', 'bar@example.org',
                          'cc@example.org', 'bcc@example.org'},
                         set(recipients))
        self._assert_mail(message, 'text/plain', 'raise-text-html')

    def test_broken_plain_and_html_formatter(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/plain')
            self._add_subscription(sid='bar', format='text/html')
        self._notify_event('raise-text-plain raise-text-html')

        history = self.sender.history
        self.assertEqual([], history)

    def test_username_in_always_cc(self):
        self.env.config.set('notification', 'smtp_always_cc',
                            'foo, cc@example.org')
        self.env.config.set('notification', 'smtp_always_bcc',
                            'bar, foo, bcc@example.org')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual({'foo@example.org', 'bar@example.org',
                          'cc@example.org', 'bcc@example.org'},
                         set(recipients))
        self.assertEqual('cc@example.org, foo@example.org', message['Cc'])
        self.assertIsNone(message['Bcc'])
        self._assert_mail(message, 'text/plain', 'blah')

    def test_from_author_disabled(self):
        self.env.config.set('notification', 'smtp_from_author', 'disabled')
        with self.env.db_transaction:
            self._add_subscription(sid='bar')

        self._notify_event('blah', author='bar')
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('My Project <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('My Project <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

        self.env.config.set('notification', 'smtp_from_name', 'Trac')
        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('Trac <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

    def test_from_author_enabled(self):
        self.env.config.set('notification', 'smtp_from_author', 'enabled')
        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='bar')

        self._notify_event('blah', author='bar')
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('bar@example.org', from_addr)
        self.assertEqual('=?utf-8?b?QsOkxZUncw==?= name <bar@example.org>',
                         message['From'])
        self.assertEqual(1, len(history))

        self._notify_event('blah', author='foo')
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('foo@example.org', from_addr)
        self.assertEqual('foo@example.org', message['From'])
        self.assertEqual(1, len(history))

        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('My Project <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

        self.env.config.set('notification', 'smtp_from_name', 'Trac')
        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('Trac <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

    def test_ignore_domains(self):
        config = self.env.config
        config.set('notification', 'smtp_always_cc',
                   'cc@example.org, cc@example.net')
        config.set('notification', 'smtp_always_bcc',
                   'bcc@example.org, bcc@example.net')
        config.set('notification', 'ignore_domains',
                   'example.org, example.com')

        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='bar')
            self._add_subscription(sid='baz')
            self._add_subscription(sid='qux')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual(set(('baz@example.net', 'qux@example.net',
                              'cc@example.net', 'bcc@example.net')),
                         set(recipients))

    def _test_without_domain(self, use_short_addr='disabled',
                             smtp_default_domain=''):
        config = self.env.config
        config.set('notification', 'use_short_addr', use_short_addr)
        config.set('notification', 'smtp_default_domain', smtp_default_domain)
        config.set('notification', 'smtp_from', 'from-trac')
        config.set('notification', 'smtp_always_cc', 'qux, cc@example.org')
        config.set('notification', 'smtp_always_bcc', 'bcc1@example.org, bcc2')
        config.set('notification', 'email_address_resolvers',
                   'SessionEmailResolver')
        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='baz')
            self._add_subscription(sid='corge')
        self._notify_event('blah')
        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        return history

    def _assert_equal_sets(self, expected, actual):
        expected = set(expected)
        actual = set(actual)
        if expected != actual:
            self.fail('%r != %r' % ((expected - actual, actual - expected)))

    def _cclist(self, cc):
        return _fixup_cc_list(cc).split(', ')

    def test_use_short_addr(self):
        history = self._test_without_domain(use_short_addr='enabled')
        from_addr, recipients, message = history[0]
        self.assertEqual('from-trac', from_addr)
        self.assertEqual('My Project <from-trac>', message['From'])
        self._assert_equal_sets(['qux', 'cc@example.org', 'bcc1@example.org',
                                 'bcc2', 'foo@example.org', 'baz',
                                 'corge-mail'], recipients)
        self._assert_equal_sets(['qux', 'cc@example.org'],
                                self._cclist(message['Cc']))

    def test_smtp_default_domain(self):
        history = self._test_without_domain(smtp_default_domain='example.com')
        from_addr, recipients, message = history[0]
        self.assertEqual('from-trac@example.com', from_addr)
        self.assertEqual('My Project <from-trac@example.com>',
                         message['From'])
        self._assert_equal_sets(['qux@example.com', 'cc@example.org',
                                 'bcc1@example.org', 'bcc2@example.com',
                                 'foo@example.org', 'baz@example.com',
                                 'corge-mail@example.com'], recipients)
        self._assert_equal_sets(['qux@example.com', 'cc@example.org'],
                                self._cclist(message['Cc']))

    def test_username_is_email(self):
        config = self.env.config
        config.set('notification', 'email_address_resolvers',
                   'SessionEmailResolver')
        with self.env.db_transaction:
            self._add_session(sid='foo@example.com')
            self._add_session(sid='bar@example.com',
                              email='foo@bar.example.org')
            self._add_subscription(sid='foo@example.com')
            self._add_subscription(sid='bar@example.com')
            self._add_subscription(sid='baz@example.com')  # no session
        self._notify_event('blah')
        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('My Project <trac@example.org>', message['From'])
        self.assertEqual({'foo@example.com', 'foo@bar.example.org',
                          'baz@example.com', 'cc@example.org',
                          'bcc@example.org'}, set(recipients))
        self._assert_equal_sets(['cc@example.org'],
                                self._cclist(message['Cc']))

    def test_replyto(self):
        config = self.env.config
        config.set('notification', 'smtp_replyto', 'replyto@example.org')
        self._notify_event('blah')
        history = self.sender.history
        from_addr, recipients, message = history[0]
        self.assertEqual('replyto@example.org', message['Reply-To'])

    def test_replyto_empty(self):
        config = self.env.config
        config.set('notification', 'smtp_replyto', '')
        self._notify_event('blah')
        history = self.sender.history
        from_addr, recipients, message = history[0]
        self.assertNotIn('Reply-To', message)


class RecipientMatcherTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.config = self.env.config

    def tearDown(self):
        self.env.reset_db()

    def _add_session(self, sid, values=None, **attrs):
        session = DetachedSession(self.env, sid)
        session['(dummy)'] = 'x'
        if values is not None:
            attrs.update(values)
        for name, value in attrs.items():
            session[name] = value
        session.save()

    def test_match_recipient_empty(self):
        matcher = RecipientMatcher(self.env)
        self.assertEqual(None, matcher.match_recipient(None))
        self.assertEqual(None, matcher.match_recipient(''))

    def test_match_recipient_anonymous(self):
        matcher = RecipientMatcher(self.env)
        self.assertEqual(None, matcher.match_recipient('anonymous'))

    def test_match_recipient_address(self):
        matcher = RecipientMatcher(self.env)
        expected = (None, 0, 'user@example.org')
        self.assertEqual(expected, matcher.match_recipient('user@example.org'))
        self.assertEqual(expected,
                         matcher.match_recipient('<user@example.org>'))
        self.assertEqual(expected, matcher.match_recipient(
            'Name name <user@example.org>'))
        self.assertEqual(expected, matcher.match_recipient(
            'Námë ńämé <user@example.org>'))

    def test_match_recipient_admit_domains(self):
        self.config.set('notification', 'admit_domains', 'LOCALDOMAIN')
        with self.env.db_transaction:
            self._add_session('user1', email='user1@localhost')
            self._add_session('user2', email='user2@localdomain')
            self._add_session('user3', email='user3@example.org')
            self._add_session('user4@localhost')
            self._add_session('user5@localdomain')
            self._add_session('user6@example.org')
            self._add_session('user7@localhost', email='user7@example.org')
            self._add_session('user8@localdomain', email='user8@localhost')
            self._add_session('user9@example.org', email='user9@localdomain')
        matcher = RecipientMatcher(self.env)

        # authenticated users
        self.assertEqual(None, matcher.match_recipient('user1'))
        self.assertEqual(('user2', 1, 'user2@localdomain'),
                         matcher.match_recipient('user2'))
        self.assertEqual(('user3', 1, 'user3@example.org'),
                         matcher.match_recipient('user3'))
        self.assertEqual(None, matcher.match_recipient('user4@localhost'))
        self.assertEqual(('user5@localdomain', 1, 'user5@localdomain'),
                         matcher.match_recipient('user5@localdomain'))
        self.assertEqual(('user6@example.org', 1, 'user6@example.org'),
                         matcher.match_recipient('user6@example.org'))
        self.assertEqual(('user7@localhost', 1, 'user7@example.org'),
                         matcher.match_recipient('user7@localhost'))
        self.assertEqual(None, matcher.match_recipient('user8@localdomain'))
        self.assertEqual(('user9@example.org', 1, 'user9@localdomain'),
                         matcher.match_recipient('user9@example.org'))
        # anonymous users
        self.assertEqual(None, matcher.match_recipient('foobar'))
        self.assertEqual(None, matcher.match_recipient('anon@localhost'))
        self.assertEqual((None, 0, 'anon@localdomain'),
                         matcher.match_recipient('anon@localdomain'))
        self.assertEqual((None, 0, 'anon@example.org'),
                         matcher.match_recipient('anon@example.org'))

    def test_match_recipient_use_short_addr(self):
        self.config.set('notification', 'use_short_addr', 'enabled')
        with self.env.db_transaction:
            self._add_session('user1')
            self._add_session('user2', email='user2-email')
            self._add_session('user3', email='user3@example.org')
            self._add_session('user4@example.org', email='user4')
        matcher = RecipientMatcher(self.env)

        self.assertEqual(('user1', 1, 'user1'),
                         matcher.match_recipient('user1'))
        self.assertEqual(('user2', 1, 'user2-email'),
                         matcher.match_recipient('user2'))
        self.assertEqual(('user3', 1, 'user3@example.org'),
                         matcher.match_recipient('user3'))
        self.assertEqual(('user4@example.org', 1, 'user4'),
                         matcher.match_recipient('user4@example.org'))
        self.assertEqual((None, 0, 'user9'), matcher.match_recipient('user9'))

    def test_match_recipient_smtp_default_domain(self):
        self.config.set('notification', 'smtp_default_domain',
                        'default.example.net')
        with self.env.db_transaction:
            self._add_session('user1')
            self._add_session('user2', email='user2-email')
            self._add_session('user3', email='user3@example.org')
            self._add_session('user4@example.org', email='user4')
            self._add_session('user5@example.org')
        matcher = RecipientMatcher(self.env)

        self.assertEqual(('user1', 1, 'user1@default.example.net'),
                         matcher.match_recipient('user1'))
        self.assertEqual(('user2', 1, 'user2-email@default.example.net'),
                         matcher.match_recipient('user2'))
        self.assertEqual(('user3', 1, 'user3@example.org'),
                         matcher.match_recipient('user3'))
        self.assertEqual(('user4@example.org', 1, 'user4@default.example.net'),
                         matcher.match_recipient('user4@example.org'))
        self.assertEqual(('user5@example.org', 1, 'user5@example.org'),
                         matcher.match_recipient('user5@example.org'))
        self.assertEqual((None, 0, 'user9@default.example.net'),
                         matcher.match_recipient('user9'))

    def test_match_recipient_ignore_domains(self):
        self.config.set('notification', 'ignore_domains',
                        'example.net,example.com')
        with self.env.db_transaction:
            self._add_session('user1', email='user1@example.org')
            self._add_session('user2', email='user2@example.com')
            self._add_session('user3', email='user3@EXAMPLE.COM')
            self._add_session('user4@example.org')
            self._add_session('user5@example.com')
            self._add_session('user6@EXAMPLE.COM')
        matcher = RecipientMatcher(self.env)

        # authenticated users
        self.assertEqual(('user1', 1, 'user1@example.org'),
                         matcher.match_recipient('user1'))
        self.assertEqual(None, matcher.match_recipient('user2'))
        self.assertEqual(None, matcher.match_recipient('user3'))
        self.assertEqual(('user4@example.org', 1, 'user4@example.org'),
                         matcher.match_recipient('user4@example.org'))
        self.assertEqual(None, matcher.match_recipient('user5@example.com'))
        self.assertEqual(None, matcher.match_recipient('user6@EXAMPLE.COM'))
        # anonymous users
        self.assertEqual((None, 0, 'anon@example.org'),
                         matcher.match_recipient('anon@example.org'))
        self.assertEqual(None, matcher.match_recipient('anon@example.com'))
        self.assertEqual(None, matcher.match_recipient('anon@EXAMPLE.COM'))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(EmailDistributorTestCase))
    suite.addTest(makeSuite(RecipientMatcherTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
